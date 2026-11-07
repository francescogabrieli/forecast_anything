# Public repository readiness

Start with the [README](../README.md) for setup, [CONTRIBUTING](../CONTRIBUTING.md) for checks, and [SECURITY](../SECURITY.md) for disclosure. Implementation guides are under `docs/implementation`, synthetic inputs under `examples` and `tests/fixtures`, and experimental evidence under `docs/research`. Review the [license](../LICENSE) and [third-party notices](../NOTICE) together.

Before changing visibility:

- Review the intended default branch and all remote branches and tags. Scan the full reachable history for credentials and review flagged fixtures and benchmark identifiers against their origin.
- Review tracked examples, screenshots and reports for private observations and operator paths. Review GitHub issues, PR descriptions and attachments, Actions logs and uploaded artifacts separately from the Git history.
- Confirm the public owner, repository name and support channels. Enable private vulnerability reporting and check repository permissions and branch protection for the intended public workflow.
- Keep local databases, credential files, model weights and built packages out of Git. Review the final release artifact separately using the release workflow and the real-model acceptance procedure.

The website and the registry release have their own publication steps. See [first release gates](first-release.md).
