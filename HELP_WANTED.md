# Help wanted

SatDeed is open to contributions. Below is the hardening work that would make it stronger, roughly in order of impact. Pick anything, comment on (or open) an issue so others know you are on it, and see [CONTRIBUTING.md](CONTRIBUTING.md) to get started.

Found a vulnerability instead? Please report it privately, see [SECURITY.md](SECURITY.md).


### Independent implementations

**High impact.** A second implementation in another language (Rust, Go, TypeScript) that passes the same examples is the strongest test of the spec. See issue #1.

### Fuzz the reference parser

**Medium.** Run Hypothesis or Atheris against the record parsing and validation code and report anything that crashes or accepts invalid data.

### Spec ambiguity hunt

**Medium.** Read the specification as an implementer and open an issue for every sentence that could be read two ways.
