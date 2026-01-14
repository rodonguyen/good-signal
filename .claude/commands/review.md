Review and test changes by interacting with the app end-to-end operations involving the changes, and visually verifying with Playwright, backend process logs, frontend console log:

1. Plan an e2e testing flow for the changes
2. Navigate to http://localhost:5173 or https://localhost:5174 using Playwright `browser_navigate`
3. Use `browser_snapshot` to capture the current UI state
4. If the user specified a page or feature, navigate to and test that specific area
5. For interactive features, test using `browser_click`, `browser_type`, etc.
6. Interact and test end-to-end to make sure the feature is integrated well / the bug is fixed
7. Report any issues found
8. Call suitable agents to iteratively fix it
9. Repeat until the issue is resolved or the feature works as expected

Arguments: $ARGUMENTS (optional - specific page or feature to verify)
