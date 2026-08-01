"""Every dialog the app opens.

The setup screen (all three monitors at once), the three per-monitor settings
dialogs and their shared base, the widgets they are built from (color scale,
company legend) and the two process-action dialogs.

Every dialog is bound to ONE `ThemeScope` at construction — a per-mode dialog
to the window that opened it, the setup screen to the app-wide scope — so two
open dialogs can be on different themes.
"""
