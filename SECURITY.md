# Security

The published quickstart is a local development profile. It uses a fixed demo identity and local database role; bind it to localhost. Provider credentials belong in an untracked environment file or secret manager.

For a suspected credential leak, authorization bypass, or exposure of a user's workspace, **do not post the secret or personal data in a public issue**. Use the repository's private vulnerability reporting option under **Security → Advisories → Report a vulnerability**, when available. Otherwise contact the maintainer through the contact details on [Aryaveer's GitHub profile](https://github.com/Veer376), sharing a non-sensitive description first.

Include the affected revision, component, prerequisites, minimal reproduction, and expected versus observed access. Never send a live provider key, service-role token, or full browser profile as evidence. Rotate exposed credentials at their provider as well as removing them from source; deleting a file does not revoke its credential.

Human approval governs the example report write. It is not an operating-system sandbox. The experimental shell/browser/local-system tools require a separate threat model before public or multi-user hosting.
