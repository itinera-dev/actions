# itinera-dev/actions

Shared GitHub Actions used by every itinera-dev repository: the pull request checks, the proposal automation and the conformance runs.

Every action is a folder holding an `action.yml` that only declares inputs and runs one command, and a Python entry point. The logic lives in the importable `lib/` package, written for the Python standard library only, and is covered by the tests under `tests/`. Repositories use a released version, for example `itinera-dev/actions/pr-has-issue@v1`.

The rules for automation in the organisation are in the [contributing guide](https://github.com/itinera-dev/.github/blob/main/CONTRIBUTING.md).

Built with AI under the terms of [A manifesto for software engineering with AI](https://marlon-sousa.com/blog/manifesto/); see [how Itinera is built](https://github.com/itinera-dev/.github/blob/main/CONTRIBUTING.md#how-itinera-is-built).

## License

Licensed under either of

- Apache License, Version 2.0 ([LICENSE-APACHE](LICENSE-APACHE) or <https://www.apache.org/licenses/LICENSE-2.0>)
- MIT license ([LICENSE-MIT](LICENSE-MIT) or <https://opensource.org/licenses/MIT>)

at your option.

### Contribution

Unless you explicitly state otherwise, any contribution intentionally submitted
for inclusion in the work by you, as defined in the Apache-2.0 license, shall be
dual licensed as above, without any additional terms or conditions.
