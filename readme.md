# fires-social-manager

A repo manifest: eleven projects across the seven sides of a hexagon.

```
repo init -u https://github.com/fire/fires-social-manager.git -b main
repo sync -j8
```

A social manager built on VRCX data. It renormalizes a VRCX SQLite database to
Essential Tuple Normal Form with deterministic UUID keys, and forecasts four
things: when a friend is likely around, who you are drifting from, where it
will be busy tonight, and what your own rhythm looks like.

**The data never leaves the machine it runs on.** These repositories are
public and hold only code. The store they build holds real people's names,
bios, movements and social graph, and those people consented to none of it
being published. `gates/check_no_personal_data.py` runs on pre-commit and on
pre-push, and blocks the push rather than trusting anyone to remember.

| side | holds | project |
| --- | --- | --- |
| `1-transport` | what triggers an interactor | `social-web` |
| `2-contract` | what transport and interactor agree on | `manuals-social-manager` |
| `3-interactor` | what computes | `normalize`, `forecast`, `forecast-timesfm`, `forecast-litert` |
| `4-entities` | what is computed about | `social-graph` |
| `5-repository` | what puts one where another finds it later | `fact-store` |
| `6-datasource` | the corpus itself | `vrcx` |
| `7-service` | a deployment set | `social-manager` |

The side a repository sits on is decided by `default.xml` and nothing else.

## Running the gates

```sh
gates/install-hooks.sh     # installs the pre-push hook, runs the controls
gates/all.sh --self-test   # the negative controls, alone
gates/all.sh               # the controls, then the gates
```

Every gate ships a negative control that asserts known-broken input FAILS. The
controls run first and unconditionally, because a gate that cannot fail proves
nothing when it passes. A silent skip is a FAIL, not a pass.

Licensed Apache-2.0 OR MIT. Two files, because dual licensing means the reader
chooses and one file cannot offer a choice.
