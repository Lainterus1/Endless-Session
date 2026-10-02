"""Единая команда сборки, установки и восстановления Endless Session."""
import argparse
import json
from pathlib import Path
import tempfile

from build_plugin import build
from install_plugin import install, restore
from migrate_plugin import migrate, restore_migration

PLUGIN_ID = "lainterus.endless-session"
LOCK_ORIGIN = Path("/usr/share/omarchy/shell/plugins/lock")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("install")
    migration = sub.add_parser("migrate")
    migration.add_argument("--legacy-backup", required=True, type=Path)
    rollback = sub.add_parser("restore")
    rollback.add_argument("--backup", required=True, type=Path)
    recover = sub.add_parser("restore-migration")
    recover.add_argument("--record", required=True, type=Path)
    args = parser.parse_args()
    home = Path.home()
    if args.action in ("install", "migrate"):
        with tempfile.TemporaryDirectory(prefix="endless-session-") as temp:
            package_path = Path(temp) / "package"
            build(package_path, PLUGIN_ID, LOCK_ORIGIN)
            if args.action == "install":
                result = {"backup": str(install(package_path, home))}
            else:
                result = {"migration_record": str(migrate(args.legacy_backup.absolute(), package_path, home))}
    elif args.action == "restore":
        result = {"phase": restore(args.backup.absolute(), home)["phase"]}
    else:
        result = {"phase": restore_migration(args.record.absolute(), home)["phase"]}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
