Review UI changes by building, linting, and visually verifying with Playwright:

4. Navigate to http://localhost:5173 or https://localhost:5174 using Playwright `browser_navigate`
5. Use `browser_snapshot` to capture the current UI state
6. If the user specified a page or feature, navigate to and test that specific area
7. For interactive features, test using `browser_click`, `browser_type`, etc.
8. Interact and test end-to-end to make sure it is integrated well
8. Report any issues found
9. Call suitable agents to iteratively fix it
10. Repeat until the issue is resolved or the feature works as expected

Arguments: $ARGUMENTS (optional - specific page or feature to verify)
