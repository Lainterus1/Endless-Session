# Attribution Notice

Endless Session builds two user-level service clones from the installed Omarchy `omarchy.lock` and `omarchy.idle` plugins. Before building, the installer checks the Omarchy version and hashes of the source files. The generated package includes modified `Service.qml`, `LockView.qml`, and `IdleModel.js` files as well as components copied from those services. They originate from [Omarchy](https://github.com/omacom/omarchy), copyright David Heinemeier Hansson, under the MIT License. The MIT notice is included in both installed plugin directories.

All other Endless Session files are distributed under the [MIT License](LICENSE). Omarchy and Codex are separate projects; this repository is not an official release of either.
