"""
Bayesian Regression Bitcoin Trading Implementation
Based on Shah & Zhang (2014) - "Bayesian Regression and Bitcoin"

This implementation adapts the paper's 10-second interval strategy to 1-minute intervals.
Window sizes are adjusted to maintain similar time coverage:
- S1: 30 bars (30 minutes)
- S2: 60 bars (60 minutes)
- S3: 120 bars (120 minutes)
"""

import numpy as np
from sklearn.cluster import KMeans
from sklearn.linear_model import LinearRegression
from typing import Tuple, List, Dict, Optional
from pathlib import Path
from dataclasses import dataclass
import hashlib
import pickle


@dataclass
class FeeConfig:
    """
    Fee configuration for trading.

    Attributes:
        round_trip_pct: Total fee for opening + closing a position (default 0.15%)
        position_size: Position size in units (default 1.0)
    """

    round_trip_pct: float = 0.0015  # 0.15% round trip
    position_size: float = 1.0  # Units traded

    def calculate_fee(self, trade_value: float) -> float:
        """Calculate fee for a round-trip trade (open + close)."""
        notional = trade_value * self.position_size
        return notional * self.round_trip_pct


class BayesianBitcoinTrader:
    """
    Bayesian regression trading strategy for crypto.

    Uses multiple timeframe patterns and order book imbalance to predict price changes.
    """

    def __init__(self, window_sizes: List[int] = [30, 60, 120], n_clusters: int = 100, n_select: int = 20):  # Adjusted for 1-minute intervals
        """
        Initialize the Bayesian trader.

        Args:
            window_sizes: Lookback windows for S1, S2, S3 (in bars)
            n_clusters: Number of k-means clusters to create
            n_select: Number of top clusters to select
        """
        self.window_sizes = window_sizes
        self.n_clusters = n_clusters
        self.n_select = n_select

        # Pattern libraries (normalized patterns) for each timeframe
        self.pattern_libs = [None, None, None]
        # Labels (price changes) for each pattern library
        self.label_libs = [None, None, None]
        # Scaling constants for each timeframe
        self.c_values = [1.0, 1.0, 1.0]
        # Combination weights [w0, w1, w2, w3, w4]
        self.weights = [0.0, 0.25, 0.25, 0.25, 0.25]

    @staticmethod
    def _generate_config_hash(window_sizes: List[int], n_clusters: int, n_select: int, dataset_length: int) -> str:
        """
        Generate a hash key based on model configuration and dataset length.

        Args:
            window_sizes: List of window sizes
            n_clusters: Number of clusters
            n_select: Number of selected clusters
            dataset_length: Length of training dataset

        Returns:
            Hash string identifier
        """
        config_str = f"{sorted(window_sizes)}_{n_clusters}_{n_select}_{dataset_length}"
        return hashlib.md5(config_str.encode()).hexdigest()

    def _get_weights_path(self, weights_dir: Path, config_hash: str) -> Path:
        """Get path to saved weights file."""
        weights_dir.mkdir(parents=True, exist_ok=True)
        return weights_dir / f"model_weights_{config_hash}.pkl"

    def save_weights(self, weights_dir: str = "bayesian_method_poc/model_weights", dataset_length: Optional[int] = None) -> Path:
        """
        Save model weights and pattern libraries to disk.

        Args:
            weights_dir: Directory to save weights
            dataset_length: Length of training dataset (for config hash)

        Returns:
            Path to saved weights file
        """
        if any(lib is None for lib in self.pattern_libs):
            raise ValueError("Cannot save weights: model has not been trained yet")

        if dataset_length is None:
            raise ValueError("dataset_length must be provided to generate config hash")

        config_hash = self._generate_config_hash(self.window_sizes, self.n_clusters, self.n_select, dataset_length)
        weights_path = self._get_weights_path(Path(weights_dir), config_hash)

        # Prepare model state
        model_state = {
            "window_sizes": self.window_sizes,
            "n_clusters": self.n_clusters,
            "n_select": self.n_select,
            "pattern_libs": self.pattern_libs,
            "label_libs": self.label_libs,
            "c_values": self.c_values,
            "weights": self.weights,
            "config_hash": config_hash,
            "dataset_length": dataset_length,
        }

        # Save as pickle
        with open(weights_path, "wb") as f:
            pickle.dump(model_state, f)

        print(f"[OK] Model weights saved to: {weights_path}")
        return weights_path

    @classmethod
    def load_weights(
        cls,
        window_sizes: List[int],
        n_clusters: int,
        n_select: int,
        dataset_length: int,
        weights_dir: str = "bayesian_method_poc/model_weights",
    ) -> Optional["BayesianBitcoinTrader"]:
        """
        Load model weights from disk if they exist.

        Args:
            window_sizes: List of window sizes
            n_clusters: Number of clusters
            n_select: Number of selected clusters
            dataset_length: Length of training dataset
            weights_dir: Directory containing weights

        Returns:
            BayesianBitcoinTrader instance with loaded weights, or None if not found
        """
        config_hash = cls._generate_config_hash(window_sizes, n_clusters, n_select, dataset_length)
        weights_path = Path(weights_dir) / f"model_weights_{config_hash}.pkl"

        if not weights_path.exists():
            return None

        try:
            with open(weights_path, "rb") as f:
                model_state = pickle.load(f)

            # Validate configuration matches
            if (
                model_state["window_sizes"] != window_sizes
                or model_state["n_clusters"] != n_clusters
                or model_state["n_select"] != n_select
                or model_state["dataset_length"] != dataset_length
            ):
                print(f"[WARNING] Config mismatch for loaded weights, skipping load")
                return None

            # Create model instance
            model = cls(window_sizes=window_sizes, n_clusters=n_clusters, n_select=n_select)
            model.pattern_libs = model_state["pattern_libs"]
            model.label_libs = model_state["label_libs"]
            model.c_values = model_state["c_values"]
            model.weights = model_state["weights"]

            print(f"[OK] Model weights loaded from: {weights_path}")
            return model

        except Exception as e:
            print(f"[WARNING] Failed to load weights: {e}")
            return None

    def normalize_pattern(self, pattern: np.ndarray) -> np.ndarray:
        """
        Normalize pattern to mean=0, std=1.
        This enables Pearson correlation as dot product.

        Args:
            pattern: Price window array

        Returns:
            Normalized pattern
        """
        mean = np.mean(pattern)
        std = np.std(pattern)

        if std == 0 or np.isnan(std):
            return np.zeros_like(pattern, dtype=np.float64)

        return (pattern - mean) / std

    def extract_patterns(self, price_series: np.ndarray, window_size: int) -> Tuple[np.ndarray, np.ndarray]:
        """
        Extract all possible patterns of given window size.
        Each pattern is a vector of consecutive prices.
        Label is the price change immediately following the pattern.

        Args:
            price_series: Array of prices
            window_size: Size of sliding window

        Returns:
            Tuple of (patterns, labels)
        """
        patterns = []
        labels = []

        for i in range(len(price_series) - window_size - 1):
            window = price_series[i : i + window_size]
            # Price change after this window
            future_change = price_series[i + window_size] - price_series[i + window_size - 1]
            patterns.append(window)
            labels.append(future_change)

        return np.array(patterns, dtype=np.float64), np.array(labels, dtype=np.float64)

    def cluster_patterns(self, patterns: np.ndarray, labels: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Cluster patterns using k-means and select top clusters based on effectiveness.

        Effectiveness = |mean price change| / std (signal-to-noise ratio)

        Args:
            patterns: Array of price patterns
            labels: Array of price change labels

        Returns:
            Tuple of (selected_patterns, selected_labels)
        """
        print(f"    Clustering {len(patterns)} patterns into {self.n_clusters} clusters...")

        # Normalize all patterns first
        normalized = np.array([self.normalize_pattern(p) for p in patterns])

        # Remove any NaN or inf values
        valid_mask = ~np.any(np.isnan(normalized) | np.isinf(normalized), axis=1)
        normalized = normalized[valid_mask]
        labels = labels[valid_mask]

        if len(normalized) < self.n_clusters:
            print(f"    WARNING: Only {len(normalized)} valid patterns, reducing clusters to {len(normalized)}")
            n_clusters = min(self.n_clusters, len(normalized))
        else:
            n_clusters = self.n_clusters

        # Cluster using k-means (with lower max_iter to save memory)
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=5, max_iter=100)
        cluster_ids = kmeans.fit_predict(normalized)

        # Evaluate each cluster by effectiveness
        cluster_scores = []
        for k in range(n_clusters):
            mask = cluster_ids == k
            cluster_labels = labels[mask]

            if len(cluster_labels) < 10:  # Skip small clusters
                cluster_scores.append(-np.inf)
                continue

            # Effectiveness = signal-to-noise ratio
            mean_change = np.abs(np.mean(cluster_labels))
            std_change = np.std(cluster_labels)

            if std_change == 0 or np.isnan(std_change):
                cluster_scores.append(-np.inf)
            else:
                cluster_scores.append(mean_change / std_change)

        # Select top clusters
        n_select = min(self.n_select, n_clusters)
        top_clusters = np.argsort(cluster_scores)[-n_select:]

        print(f"    Selected top {n_select} clusters")
        print(f"    Best cluster score: {np.max(cluster_scores):.4f}")

        # Get representative patterns (cluster centers)
        selected_patterns = kmeans.cluster_centers_[top_clusters]

        # Get average labels for each selected cluster
        selected_labels = []
        for k in top_clusters:
            mask = cluster_ids == k
            selected_labels.append(np.mean(labels[mask]))

        return selected_patterns, np.array(selected_labels, dtype=np.float64)

    def similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """
        Compute Pearson correlation between two patterns.
        For normalized patterns, this is just the dot product / length.

        Args:
            a: First pattern (normalized)
            b: Second pattern (normalized)

        Returns:
            Similarity score
        """
        if len(a) == 0:
            return 0.0
        return np.dot(a, b) / len(a)

    def predict_single_timeframe(self, current_pattern: np.ndarray, pattern_library: np.ndarray, labels: np.ndarray, c: float) -> float:
        """
        Generate prediction using one timeframe's pattern library.

        Uses the formula:
        y_hat = sum(y_i * exp(c * s(x, x_i))) / sum(exp(c * s(x, x_i)))

        Args:
            current_pattern: Current price window (raw)
            pattern_library: Pre-normalized pattern library
            labels: Price change labels for each pattern
            c: Scaling constant

        Returns:
            Predicted price change
        """
        # Normalize current pattern
        current_norm = self.normalize_pattern(current_pattern)

        # Compute similarities with all patterns in library
        similarities = np.dot(pattern_library, current_norm) / len(current_norm)

        # Compute weights using exponential
        weights = np.exp(c * similarities)

        # Avoid division by zero
        total_weight = np.sum(weights)
        if total_weight == 0 or np.isnan(total_weight):
            return 0.0

        # Weighted average of labels
        prediction = np.sum(weights * labels) / total_weight

        return prediction

    def fit(self, price_series: np.ndarray, imbalance_ratios: np.ndarray = None) -> "BayesianBitcoinTrader":
        """
        Train the model on historical data.

        Splits data into three periods:
        - Period 1 (1/3): Pattern extraction
        - Period 2 (1/3): Weight training
        - Period 3 (1/3): Testing (not used in fit)

        Args:
            price_series: Array of close prices
            imbalance_ratios: Array of order book imbalance ratios (optional)

        Returns:
            Self for chaining
        """
        import sys

        print(f"\n{'='*60}")
        print("TRAINING BAYESIAN REGRESSION MODEL")
        print(f"{'='*60}")
        print(f"Total data points: {len(price_series)}")
        sys.stdout.flush()

        n = len(price_series)
        split1 = n // 3
        split2 = 2 * n // 3

        # Period 1: Pattern extraction (first 1/3)
        pattern_data = price_series[:split1]
        print(f"\nPeriod 1 (Pattern Extraction): {len(pattern_data)} points")
        print(f"  Date range: index 0 to {split1}")
        sys.stdout.flush()

        # Extract and cluster patterns for each timeframe
        for i, ws in enumerate(self.window_sizes):
            print(f"\n  [LOG] Starting timeframe {i+1}/{len(self.window_sizes)}: Window size = {ws} bars ({ws} minutes)")
            sys.stdout.flush()

            print(f"    [LOG] Extracting patterns...")
            sys.stdout.flush()
            patterns, labels = self.extract_patterns(pattern_data, ws)
            print(f"    [OK] Extracted {len(patterns)} patterns")
            sys.stdout.flush()

            print(f"    [LOG] Clustering patterns (this may take a minute)...")
            sys.stdout.flush()
            self.pattern_libs[i], self.label_libs[i] = self.cluster_patterns(patterns, labels)
            print(f"    [OK] Pattern library created: {len(self.pattern_libs[i])} patterns")
            sys.stdout.flush()

        # Period 2: Weight training (second 1/3)
        train_data = price_series[split1:split2]
        train_imbalance = imbalance_ratios[split1:split2] if imbalance_ratios is not None else None

        print(f"\nPeriod 2 (Weight Training): {len(train_data)} points")
        print(f"  Date range: index {split1} to {split2}")
        sys.stdout.flush()

        # Optimize scaling constants (simplified: use fixed values for now)
        print(f"\n  [LOG] Using fixed scaling constants c = [1.0, 1.0, 1.0]")
        sys.stdout.flush()

        # Optimize combination weights using linear regression
        print(f"\n  [LOG] Learning combination weights (generating training predictions)...")
        sys.stdout.flush()
        self.weights = self._optimize_weights(train_data, train_imbalance)
        print(
            f"  [OK] Learned weights: w0={self.weights[0]:.4f}, w1={self.weights[1]:.4f}, "
            + f"w2={self.weights[2]:.4f}, w3={self.weights[3]:.4f}, w4={self.weights[4]:.4f}"
        )
        sys.stdout.flush()

        print(f"\n{'='*60}")
        print("TRAINING COMPLETE")
        print(f"{'='*60}\n")
        sys.stdout.flush()

        return self

    def fit_with_cache(
        self,
        price_series: np.ndarray,
        imbalance_ratios: np.ndarray = None,
        weights_dir: str = "bayesian_method_poc/model_weights",
        force_retrain: bool = False,
    ) -> "BayesianBitcoinTrader":
        """
        Train the model, loading weights from cache if available and config matches.

        Args:
            price_series: Array of close prices
            imbalance_ratios: Array of order book imbalance ratios (optional)
            weights_dir: Directory to save/load weights
            force_retrain: If True, ignore cached weights and retrain

        Returns:
            Self for chaining
        """
        dataset_length = len(price_series)

        # Try to load weights if not forcing retrain
        if not force_retrain:
            loaded_model = self.load_weights(self.window_sizes, self.n_clusters, self.n_select, dataset_length, weights_dir)
            if loaded_model is not None:
                # Copy loaded state to self
                self.pattern_libs = loaded_model.pattern_libs
                self.label_libs = loaded_model.label_libs
                self.c_values = loaded_model.c_values
                self.weights = loaded_model.weights
                print(f"[OK] Using cached weights, skipping training")
                return self

        # Train model
        self.fit(price_series, imbalance_ratios)

        # Save weights after training
        try:
            self.save_weights(weights_dir, dataset_length)
        except Exception as e:
            print(f"[WARNING] Failed to save weights: {e}")

        return self

    def _optimize_weights(self, train_data: np.ndarray, train_imbalance: np.ndarray = None) -> List[float]:
        """
        Learn optimal combination weights using linear regression.

        Args:
            train_data: Training price series
            train_imbalance: Training imbalance ratios (optional)

        Returns:
            List of weights [w0, w1, w2, w3, w4]
        """
        import sys

        X = []
        y = []

        lookback_max = max(self.window_sizes)
        total_samples = len(train_data) - lookback_max - 1

        print(f"    [LOG] Generating {total_samples} training predictions...")
        sys.stdout.flush()

        # Generate predictions for each training point
        progress_interval = max(1, total_samples // 10)  # Print every 10%
        for idx, t in enumerate(range(lookback_max, len(train_data) - 1)):
            if idx % progress_interval == 0:
                print(f"      Progress: {idx}/{total_samples} ({idx/total_samples*100:.0f}%)")
                sys.stdout.flush()

            # Extract patterns for each timeframe
            predictions = []
            for i, ws in enumerate(self.window_sizes):
                if t < ws:
                    predictions.append(0.0)
                else:
                    current = train_data[t - ws : t]
                    pred = self.predict_single_timeframe(current, self.pattern_libs[i], self.label_libs[i], self.c_values[i])
                    predictions.append(pred)

            # Add imbalance ratio
            r = train_imbalance[t] if train_imbalance is not None else 0.0

            X.append(predictions + [r])

            # Actual price change
            actual_change = train_data[t + 1] - train_data[t]
            y.append(actual_change)

        X = np.array(X)
        y = np.array(y)

        print(f"    [LOG] Fitting linear regression on {len(X)} samples...")
        sys.stdout.flush()

        # Fit linear regression
        model = LinearRegression()
        model.fit(X, y)

        w0 = model.intercept_
        w1, w2, w3, w4 = model.coef_

        return [w0, w1, w2, w3, w4]

    def predict(self, price_series: np.ndarray, t: int, r: float = 0.0) -> float:
        """
        Predict price change at time t.

        Args:
            price_series: Full price series
            t: Current time index
            r: Order book imbalance ratio

        Returns:
            Predicted price change
        """
        predictions = []

        for i, ws in enumerate(self.window_sizes):
            if t < ws:
                predictions.append(0.0)
            else:
                current = price_series[t - ws : t]
                pred = self.predict_single_timeframe(current, self.pattern_libs[i], self.label_libs[i], self.c_values[i])
                predictions.append(pred)

        # Combine predictions: delta_p = w0 + w1*dp1 + w2*dp2 + w3*dp3 + w4*r
        w0, w1, w2, w3, w4 = self.weights
        delta_p = w0 + w1 * predictions[0] + w2 * predictions[1] + w3 * predictions[2] + w4 * r

        return delta_p


class TradingStrategy:
    """
    Simple position-based trading strategy.
    Position: -1 (short), 0 (neutral), +1 (long)
    """

    def __init__(self, threshold: float):
        """
        Initialize strategy.

        Args:
            threshold: Minimum predicted change to trigger trade
        """
        self.position = 0
        self.threshold = threshold
        self.trades = []
        self.entry_price = None

    def decide(self, delta_p: float, current_price: float, timestamp: int) -> str:
        """
        Make trading decision based on predicted price change.

        Args:
            delta_p: Predicted price change
            current_price: Current market price
            timestamp: Current time index

        Returns:
            Action string: 'BUY', 'SELL', or 'HOLD'
        """
        action = "HOLD"

        if delta_p > self.threshold and self.position <= 0:
            action = "BUY"
            if self.position == -1:
                # Close short first
                self.trades.append(
                    {
                        "type": "CLOSE_SHORT",
                        "price": current_price,
                        "timestamp": timestamp,
                        "entry_price": self.entry_price,
                        "pnl": self.entry_price - current_price,  # Profit from short
                    }
                )

            self.position = 1
            self.entry_price = current_price
            self.trades.append({"type": "OPEN_LONG", "price": current_price, "timestamp": timestamp, "entry_price": current_price, "pnl": 0.0})

        elif delta_p < -self.threshold and self.position >= 0:
            action = "SELL"
            if self.position == 1:
                # Close long first
                self.trades.append(
                    {
                        "type": "CLOSE_LONG",
                        "price": current_price,
                        "timestamp": timestamp,
                        "entry_price": self.entry_price,
                        "pnl": current_price - self.entry_price,  # Profit from long
                    }
                )

            self.position = -1
            self.entry_price = current_price
            self.trades.append({"type": "OPEN_SHORT", "price": current_price, "timestamp": timestamp, "entry_price": current_price, "pnl": 0.0})

        return action

    def close_position(self, current_price: float, timestamp: int):
        """Close any open position at the end."""
        if self.position == 1:
            self.trades.append(
                {
                    "type": "CLOSE_LONG",
                    "price": current_price,
                    "timestamp": timestamp,
                    "entry_price": self.entry_price,
                    "pnl": current_price - self.entry_price,
                }
            )
            self.position = 0
        elif self.position == -1:
            self.trades.append(
                {
                    "type": "CLOSE_SHORT",
                    "price": current_price,
                    "timestamp": timestamp,
                    "entry_price": self.entry_price,
                    "pnl": self.entry_price - current_price,
                }
            )
            self.position = 0


class TradingStrategyWithSL:
    """
    Enhanced trading strategy with dynamic stop-loss and fee calculation.
    Uses pluggable stop-loss strategies from stop_loss_strategies.py.
    """

    def __init__(self, threshold: float, stop_strategy: "StopLossStrategy" = None, fee_config: FeeConfig = None):
        """
        Initialize strategy with stop-loss and fees.

        Args:
            threshold: Minimum predicted change to trigger trade
            stop_strategy: StopLossStrategy instance (default: TimeframeDisagreementStop)
            fee_config: FeeConfig instance (default: 0.15% round trip)
        """
        self.threshold = threshold
        self.position = 0
        self.trades = []
        self.entry_price = None
        self.entry_timestamp = None
        self.bars_in_trade = 0
        self.fee_config = fee_config or FeeConfig()
        self.total_fees = 0.0

        # Import here to avoid circular imports
        if stop_strategy is None:
            from stop_loss_strategies import TimeframeDisagreementStop

            self.stop_strategy = TimeframeDisagreementStop()
        else:
            self.stop_strategy = stop_strategy

    def _create_stop_context(self, current_price: float, delta_p: float, dp1: float, dp2: float, dp3: float, timestamp):
        """Create context for stop-loss evaluation."""
        from stop_loss_strategies import StopContext

        return StopContext(
            position=self.position,
            entry_price=self.entry_price or current_price,
            current_price=current_price,
            delta_p=delta_p,
            dp1=dp1,
            dp2=dp2,
            dp3=dp3,
            timestamp=timestamp,
            bars_in_trade=self.bars_in_trade,
        )

    def _close_position(self, current_price: float, timestamp, exit_reason: str) -> None:
        """Close current position and record trade with fees."""
        if self.position == 0:
            return

        if self.position == 1:
            gross_pnl = current_price - self.entry_price
            trade_type = "CLOSE_LONG"
        else:
            gross_pnl = self.entry_price - current_price
            trade_type = "CLOSE_SHORT"

        # Calculate fee based on trade value (use average of entry and exit price)
        trade_value = (self.entry_price + current_price) / 2
        fee = self.fee_config.calculate_fee(trade_value)
        net_pnl = gross_pnl - fee
        self.total_fees += fee

        self.trades.append(
            {
                "type": trade_type,
                "price": current_price,
                "timestamp": timestamp,
                "entry_price": self.entry_price,
                "entry_timestamp": self.entry_timestamp,
                "gross_pnl": gross_pnl,
                "fee": fee,
                "pnl": net_pnl,  # pnl is now net (after fees)
                "exit_reason": exit_reason,
                "bars_held": self.bars_in_trade,
            }
        )

        # Notify stop strategy
        self.stop_strategy.on_exit()

        # Reset position
        self.position = 0
        self.entry_price = None
        self.entry_timestamp = None
        self.bars_in_trade = 0

    def _open_position(self, direction: int, current_price: float, timestamp, delta_p: float, dp1: float, dp2: float, dp3: float) -> None:
        """Open a new position."""
        self.position = direction
        self.entry_price = current_price
        self.entry_timestamp = timestamp
        self.bars_in_trade = 0

        trade_type = "OPEN_LONG" if direction == 1 else "OPEN_SHORT"
        self.trades.append({"type": trade_type, "price": current_price, "timestamp": timestamp, "entry_price": current_price, "pnl": 0.0})

        # Notify stop strategy of entry
        ctx = self._create_stop_context(current_price, delta_p, dp1, dp2, dp3, timestamp)
        self.stop_strategy.on_entry(ctx)

    def decide(self, delta_p: float, current_price: float, timestamp, dp1: float = 0.0, dp2: float = 0.0, dp3: float = 0.0) -> str:
        """
        Make trading decision with stop-loss checking.

        Args:
            delta_p: Combined predicted price change
            current_price: Current market price
            timestamp: Current time index
            dp1: S1 (180-bar) prediction
            dp2: S2 (360-bar) prediction
            dp3: S3 (720-bar) prediction

        Returns:
            Action string: 'BUY', 'SELL', 'STOP_EXIT', or 'HOLD'
        """
        # Increment bars in trade
        if self.position != 0:
            self.bars_in_trade += 1

        # Check stop-loss first
        if self.position != 0:
            ctx = self._create_stop_context(current_price, delta_p, dp1, dp2, dp3, timestamp)
            should_exit, exit_reason = self.stop_strategy.should_exit(ctx)

            if should_exit:
                self._close_position(current_price, timestamp, exit_reason)
                return "STOP_EXIT"

        # Entry/reversal logic
        action = "HOLD"

        if delta_p > self.threshold and self.position <= 0:
            # Close short if exists
            if self.position == -1:
                self._close_position(current_price, timestamp, "signal_reversal")

            # Open long
            self._open_position(1, current_price, timestamp, delta_p, dp1, dp2, dp3)
            action = "BUY"

        elif delta_p < -self.threshold and self.position >= 0:
            # Close long if exists
            if self.position == 1:
                self._close_position(current_price, timestamp, "signal_reversal")

            # Open short
            self._open_position(-1, current_price, timestamp, delta_p, dp1, dp2, dp3)
            action = "SELL"

        return action

    def close_position(self, current_price: float, timestamp) -> None:
        """Close any open position at end of backtest."""
        if self.position != 0:
            self._close_position(current_price, timestamp, "end_of_period")

    def get_stop_exit_stats(self) -> Dict:
        """Get statistics on stop-loss exits and fees."""
        closes = [t for t in self.trades if "CLOSE" in t["type"]]
        if not closes:
            return {}

        stop_exits = [t for t in closes if t.get("exit_reason", "").startswith(self.stop_strategy.name)]
        signal_exits = [t for t in closes if t.get("exit_reason") == "signal_reversal"]
        eop_exits = [t for t in closes if t.get("exit_reason") == "end_of_period"]

        stop_pnls = [t["pnl"] for t in stop_exits]
        signal_pnls = [t["pnl"] for t in signal_exits]

        # Fee stats
        total_fees = sum(t.get("fee", 0) for t in closes)
        total_gross_pnl = sum(t.get("gross_pnl", t.get("pnl", 0)) for t in closes)
        total_net_pnl = sum(t.get("pnl", 0) for t in closes)

        return {
            "total_exits": len(closes),
            "stop_exits": len(stop_exits),
            "signal_exits": len(signal_exits),
            "eop_exits": len(eop_exits),
            "stop_exit_pct": len(stop_exits) / len(closes) * 100 if closes else 0,
            "avg_stop_pnl": np.mean(stop_pnls) if stop_pnls else 0,
            "avg_signal_pnl": np.mean(signal_pnls) if signal_pnls else 0,
            "stop_win_rate": np.mean([p > 0 for p in stop_pnls]) * 100 if stop_pnls else 0,
            "signal_win_rate": np.mean([p > 0 for p in signal_pnls]) * 100 if signal_pnls else 0,
            # Fee stats
            "total_fees": total_fees,
            "total_gross_pnl": total_gross_pnl,
            "total_net_pnl": total_net_pnl,
            "fee_pct_of_gross": (total_fees / total_gross_pnl * 100) if total_gross_pnl > 0 else 0,
        }


def run_backtest_with_sl(
    test_data: np.ndarray,
    test_imbalance: np.ndarray,
    model: BayesianBitcoinTrader,
    threshold: float,
    stop_strategy: "StopLossStrategy" = None,
    fee_config: FeeConfig = None,
) -> Tuple[List[Dict], List[Dict], Dict]:
    """
    Run backtest with dynamic stop-loss and fees.

    Args:
        test_data: Test price series
        test_imbalance: Test imbalance ratios
        model: Trained Bayesian model
        threshold: Trading threshold
        stop_strategy: StopLossStrategy instance (default: TimeframeDisagreementStop)
        fee_config: FeeConfig instance (default: 0.15% round trip)

    Returns:
        Tuple of (results, trades, stop_stats)
    """
    import sys

    # Import stop strategy if not provided
    if stop_strategy is None:
        from stop_loss_strategies import TimeframeDisagreementStop

        stop_strategy = TimeframeDisagreementStop()

    # Default fee config
    if fee_config is None:
        fee_config = FeeConfig()

    print(f"\n{'='*60}")
    print("RUNNING BACKTEST WITH DYNAMIC STOP-LOSS")
    print(f"{'='*60}")
    print(f"Test period: {len(test_data)} data points")
    print(f"Threshold: {threshold}")
    print(f"Stop Strategy: {stop_strategy.name}")
    print(f"Fees: {fee_config.round_trip_pct*100:.3f}% round trip")
    sys.stdout.flush()

    strategy = TradingStrategyWithSL(threshold, stop_strategy, fee_config)
    results = []

    lookback_max = max(model.window_sizes)
    total_steps = len(test_data) - lookback_max

    print(f"[LOG] Running {total_steps} predictions with SL...")
    sys.stdout.flush()

    progress_interval = max(1, total_steps // 10)

    for idx, t in enumerate(range(lookback_max, len(test_data))):
        if idx % progress_interval == 0:
            print(f"  Progress: {idx}/{total_steps} ({idx/total_steps*100:.0f}%)")
            sys.stdout.flush()

        # Get order book imbalance
        r = test_imbalance[t] if test_imbalance is not None else 0.0

        # Get per-timeframe predictions for stop-loss evaluation
        dp1 = model.predict_single_timeframe(test_data[t - model.window_sizes[0] : t], model.pattern_libs[0], model.label_libs[0], model.c_values[0])
        dp2 = model.predict_single_timeframe(test_data[t - model.window_sizes[1] : t], model.pattern_libs[1], model.label_libs[1], model.c_values[1])
        dp3 = model.predict_single_timeframe(test_data[t - model.window_sizes[2] : t], model.pattern_libs[2], model.label_libs[2], model.c_values[2])

        # Combined prediction
        delta_p = model.predict(test_data, t, r)

        # Execute decision with stop-loss checking
        current_price = test_data[t]
        action = strategy.decide(delta_p, current_price, t, dp1, dp2, dp3)

        results.append(
            {
                "timestamp": t,
                "price": current_price,
                "prediction": delta_p,
                "dp1": dp1,
                "dp2": dp2,
                "dp3": dp3,
                "action": action,
                "position": strategy.position,
            }
        )

    # Close any remaining position
    if strategy.position != 0:
        strategy.close_position(test_data[-1], len(test_data) - 1)

    # Get stop-loss statistics
    stop_stats = strategy.get_stop_exit_stats()

    print(f"\n[OK] Backtest with SL complete")
    print(f"Total trades: {len(strategy.trades)}")
    print(f"Stop exits: {stop_stats.get('stop_exits', 0)} ({stop_stats.get('stop_exit_pct', 0):.1f}%)")
    print(f"Signal exits: {stop_stats.get('signal_exits', 0)}")
    print(f"{'='*60}\n")
    sys.stdout.flush()

    return results, strategy.trades, stop_stats


def run_backtest(test_data: np.ndarray, test_imbalance: np.ndarray, model: BayesianBitcoinTrader, threshold: float) -> Tuple[List[Dict], List[Dict]]:
    """
    Run complete backtest on test period.

    Args:
        test_data: Test price series
        test_imbalance: Test imbalance ratios
        model: Trained Bayesian model
        threshold: Trading threshold

    Returns:
        Tuple of (results, trades)
    """
    import sys

    print(f"\n{'='*60}")
    print("RUNNING BACKTEST")
    print(f"{'='*60}")
    print(f"Test period: {len(test_data)} data points")
    print(f"Threshold: {threshold}")
    sys.stdout.flush()

    strategy = TradingStrategy(threshold)
    results = []

    lookback_max = max(model.window_sizes)
    total_steps = len(test_data) - lookback_max

    print(f"[LOG] Running {total_steps} predictions...")
    sys.stdout.flush()

    progress_interval = max(1, total_steps // 10)  # Print every 10%

    for idx, t in enumerate(range(lookback_max, len(test_data))):
        if idx % progress_interval == 0:
            print(f"  Progress: {idx}/{total_steps} ({idx/total_steps*100:.0f}%)")
            sys.stdout.flush()

        # Get order book imbalance
        r = test_imbalance[t] if test_imbalance is not None else 0.0

        # Generate prediction
        delta_p = model.predict(test_data, t, r)

        # Execute decision
        current_price = test_data[t]
        action = strategy.decide(delta_p, current_price, t)

        results.append({"timestamp": t, "price": current_price, "prediction": delta_p, "action": action, "position": strategy.position})

    # Close any remaining position
    if strategy.position != 0:
        strategy.close_position(test_data[-1], len(test_data) - 1)

    print(f"\n[OK] Backtest complete")
    print(f"Total trades: {len(strategy.trades)}")
    print(f"{'='*60}\n")
    sys.stdout.flush()

    return results, strategy.trades


def calculate_metrics(trades: List[Dict], start_price: float, end_price: float) -> Dict:
    """
    Calculate comprehensive performance metrics.

    Args:
        trades: List of trade dictionaries
        start_price: Starting price
        end_price: Ending price

    Returns:
        Dictionary of performance metrics
    """
    if len(trades) == 0:
        return {}

    # Extract completed trades (close trades with PnL)
    completed_trades = [t for t in trades if "CLOSE" in t["type"]]

    if len(completed_trades) == 0:
        return {}

    # Net profits (after fees if available)
    profits = np.array([t["pnl"] for t in completed_trades])

    # Gross profits (before fees) - use pnl if gross_pnl not available
    gross_profits = np.array([t.get("gross_pnl", t["pnl"]) for t in completed_trades])

    # Total fees
    total_fees = sum(t.get("fee", 0) for t in completed_trades)

    total_profit = np.sum(profits)
    total_gross_profit = np.sum(gross_profits)
    avg_profit = np.mean(profits)
    win_rate = np.mean(profits > 0)

    # Calculate Sharpe ratio as per paper
    C = abs(end_price - start_price)  # Buy-and-hold return
    L = len(completed_trades)
    std_profit = np.std(profits)

    if std_profit == 0 or L == 0:
        sharpe = 0.0
    else:
        sharpe = (total_profit - C) / (L * std_profit)

    # Maximum drawdown (on net profits)
    cumulative = np.cumsum(profits)
    running_max = np.maximum.accumulate(cumulative)
    drawdown = running_max - cumulative
    max_drawdown = np.max(drawdown) if len(drawdown) > 0 else 0

    metrics = {
        "total_trades": len(trades),
        "completed_trades": len(completed_trades),
        "total_profit": total_profit,
        "total_gross_profit": total_gross_profit,
        "total_fees": total_fees,
        "avg_profit_per_trade": avg_profit,
        "win_rate": win_rate,
        "max_profit": np.max(profits),
        "max_loss": np.min(profits),
        "profit_std": std_profit,
        "sharpe_ratio": sharpe,
        "max_drawdown": max_drawdown,
        "buy_hold_return": C,
        "return_pct": (total_profit / start_price) * 100 if start_price > 0 else 0,
        "gross_return_pct": (total_gross_profit / start_price) * 100 if start_price > 0 else 0,
    }

    return metrics


def print_performance_report(metrics: Dict, test_period_days: float):
    """Print formatted performance report."""
    print(f"\n{'='*60}")
    print("PERFORMANCE REPORT")
    print(f"{'='*60}")
    print(f"Test Period: {test_period_days:.1f} days")
    print(f"\nTRADING ACTIVITY:")
    print(f"  Total Trades: {metrics.get('total_trades', 0)}")
    print(f"  Completed Trades: {metrics.get('completed_trades', 0)}")
    print(f"\nPROFITABILITY (GROSS - before fees):")
    print(f"  Gross Profit: ${metrics.get('total_gross_profit', metrics.get('total_profit', 0)):.2f}")
    print(f"  Gross Return: {metrics.get('gross_return_pct', metrics.get('return_pct', 0)):.2f}%")
    print(f"\nFEES:")
    print(f"  Total Fees: ${metrics.get('total_fees', 0):.2f}")
    print(f"\nPROFITABILITY (NET - after fees):")
    print(f"  Net Profit: ${metrics.get('total_profit', 0):.2f}")
    print(f"  Net Return: {metrics.get('return_pct', 0):.2f}%")
    print(f"  Avg Profit/Trade: ${metrics.get('avg_profit_per_trade', 0):.2f}")
    print(f"  Win Rate: {metrics.get('win_rate', 0)*100:.1f}%")
    print(f"\nRISK METRICS:")
    print(f"  Sharpe Ratio: {metrics.get('sharpe_ratio', 0):.2f}")
    print(f"  Max Drawdown: ${metrics.get('max_drawdown', 0):.2f}")
    print(f"  Profit Std Dev: ${metrics.get('profit_std', 0):.2f}")
    print(f"\nBENCHMARK:")
    print(f"  Buy & Hold: ${metrics.get('buy_hold_return', 0):.2f}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    print("Bayesian Bitcoin Trader - POC Implementation")
    print("Based on Shah & Zhang (2014)\n")
