import pandas as pd
import numpy as np

# Load latest trade log
df = pd.read_csv('results/trades_20251225_185112.csv')

# Filter to only closing trades (which have PnL)
closes = df[df['type'].str.contains('CLOSE')]

print("="*60)
print("TRADE ANALYSIS - Full Dataset Run")
print("="*60)

print("\nTrade PnL Distribution:")
print(closes['pnl'].describe())

wins = closes['pnl'] > 0
losses = closes['pnl'] <= 0

print("\n" + "="*60)
print("Win/Loss Breakdown:")
print("="*60)
print(f"Total Completed Trades: {len(closes)}")
print(f"Wins: {wins.sum()} ({wins.mean()*100:.1f}%)")
print(f"Losses: {losses.sum()} ({losses.mean()*100:.1f}%)")
print(f"\nAvg Win: ${closes[wins]['pnl'].mean():.2f}")
print(f"Avg Loss: ${closes[losses]['pnl'].mean():.2f}")
print(f"Win/Loss Ratio: {abs(closes[wins]['pnl'].mean() / closes[losses]['pnl'].mean()):.2f}")

print("\n" + "="*60)
print("Profit Distribution:")
print("="*60)
print(f"Largest Win: ${closes['pnl'].max():.2f}")
print(f"Largest Loss: ${closes['pnl'].min():.2f}")
print(f"Median PnL: ${closes['pnl'].median():.2f}")

# Cumulative PnL
cumulative = closes['pnl'].cumsum()
print("\n" + "="*60)
print("Cumulative Performance:")
print("="*60)
print(f"Starting PnL: $0.00")
print(f"Peak PnL: ${cumulative.max():.2f}")
print(f"Final PnL: ${cumulative.iloc[-1]:.2f}")
print(f"Max Drawdown from Peak: ${cumulative.max() - cumulative.iloc[-1]:.2f}")

print("\n" + "="*60)
print("Key Insight:")
print("="*60)
if wins.mean() > 0.5 and closes['pnl'].sum() < 0:
    avg_win = closes[wins]['pnl'].mean()
    avg_loss = abs(closes[losses]['pnl'].mean())
    print(f"High win rate ({wins.mean()*100:.1f}%) but NEGATIVE returns")
    print(f"Problem: Avg loss (${avg_loss:.2f}) is {avg_loss/avg_win:.2f}x larger than avg win (${avg_win:.2f})")
    print("Solution: Need better risk management or threshold optimization")
else:
    print("Model needs improvement in prediction accuracy")
