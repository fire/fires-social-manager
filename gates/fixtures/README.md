# Gate fixtures

Input for the negative controls. Both G0 and G4 skip this directory, because a
gate's own examples of what it forbids would otherwise trip it -- a spam filter
necessarily contains spam.

Every identifier here is **synthetic**. It is structurally a valid VRChat id so
the patterns fire, but it belongs to nobody, so committing it publishes
nothing. The reserved all-zero namespace is not used, because both gates
whitelist that and a control built on it would never fail.
