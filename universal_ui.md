# Universal UI Patterns

## Button Feedback System

All buttons that trigger async operations must provide visual feedback using this pattern:

1. **Disable the button** while the operation runs
2. **Show status text** (e.g., "Uploading...") in the global `action_status` component
3. **Re-enable the button** and clear status when complete

### Setup

Add the `action_status` component near the top of your UI, after any status message area:

```python
status_msg = gr.Markdown("", elem_id="status_msg")
action_status = gr.Markdown("", elem_id="action_status")
```

### Helper Method

Add this method to your workflow class:

```python
def _wrap_button_click(self, btn, handler, inputs, outputs, action_status, action_text="Processing..."):
    """Wrap a button click with loading state management."""
    btn.click(
        fn=lambda: (gr.update(interactive=False), f"⏳ {action_text}"),
        outputs=[btn, action_status]
    ).then(
        fn=handler,
        inputs=inputs,
        outputs=outputs
    ).then(
        fn=lambda: (gr.update(interactive=True), ""),
        outputs=[btn, action_status]
    )
```

### Usage

Instead of:

```python
my_btn.click(
    fn=handle_something,
    inputs=[state, input1],
    outputs=[state, result],
)
```

Use:

```python
self._wrap_button_click(
    my_btn,
    handle_something,
    inputs=[state, input1],
    outputs=[state, result],
    action_status=action_status,
    action_text="Doing something...",
)
```

### Action Text Guidelines

Use present participle form ending in "...":

| Operation | Action Text |
|-----------|-------------|
| Create | "Creating..." |
| Load | "Loading..." |
| Save | "Saving..." |
| Upload | "Uploading..." |
| Export | "Exporting..." |
| Generate | "Generating..." |
| Refresh | "Refreshing..." |
| Search | "Searching..." |
| Validate | "Validating..." |

Be specific when helpful: "Generating test...", "Exporting PDF...", "Loading config..."
