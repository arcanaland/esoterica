# esoterica

This repository contains esoterica data for tarot, such as card interpretations, astrological correspondences and free-form card-related passages packaged in Arcana Land's Esoterica Specification ([arcanaland/specifications](https://github.com/arcanaland/specifications)).

## Building

Assuming you have `uv` and `just`.

```
$ just list
Available recipes:
    build             # Rebuild all esoterica files in dist/
    check             # Run all of the gates
    coverage *sources # Check if every input line is mapped or known dropped
    fmt               # Write the formatting and the fixable lint
    lint              # Formatting and lint
    test *args        # The workspace's tests
    validate *files   # quick and dirty validator
    verify-input      # Verify hash of vendored source input
```

## Licensing

Most of the useful data in this repo is licensed under [`LicenseRef-McElroy-Uncopyright`](./LICENSES/LicenseRef-McElroy-Uncopyright.txt). Basically, thanks Mark McElroy!

This repository uses REUSE which should be consulted for details.
