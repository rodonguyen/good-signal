

- For complex project, think extra hard on architecture design, use appropriate design patterns, make it easy to subtitute, extend or maintain.
- Revise and refactor if the code is not satisfactory to SOLID principles.
- Ask questions if the provided instruction is unclear or has missing information. The implementation / plan has to be up to production level.


## Rules
- Trading app requires precision so NO default values or fallback recklessly, everything must be visible for user and in user's control, require user input


## UI Verification (Playwright MCP)

After implementing any related logic changes that could affect frontend or frontend changes, ALWAYS verify using Playwright MCP:
1. Use `browser_navigate` to open the relevant page
2. Use `browser_snapshot` to capture and verify the UI state
3. If issues are found, fix them before marking the task complete
4. For interactive features, test the functionality using `browser_click`, `browser_type`, etc.