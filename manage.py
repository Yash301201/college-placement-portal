#!/usr/bin/env python
import os
import sys

import pymysql

# PyMySQL speaks the MySQLdb interface Django expects.
pymysql.version_info = (2, 2, 1, "final", 0)
pymysql.install_as_MySQLdb()


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
