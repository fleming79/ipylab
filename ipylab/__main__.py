# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

def launch():
    import sys  # noqa: PLC0415

    from jupyterlab.labapp import LabApp  # noqa: PLC0415

    if not sys.argv:
        sys.argv = ["--IdentityProvider.token=''"]
    sys.exit(LabApp.launch_instance())

if __name__ == "__main__":
    launch()
