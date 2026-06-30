# ipylab

![Github Actions Status](https://github.com/jtpio/ipylab/workflows/Build/badge.svg)
[![JupyterLite](https://jupyterlite.rtfd.io/en/latest/_static/badge-launch.svg)](https://ipylab.readthedocs.io/en/latest/lite/lab)
[![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/jtpio/ipylab/main?urlpath=lab/tree/examples/widgets.ipynb)
[![Conda Version](https://img.shields.io/conda/vn/conda-forge/ipylab.svg)](https://anaconda.org/conda-forge/ipylab)
[![pypi](https://img.shields.io/pypi/v/ipylab.svg)](https://pypi.python.org/pypi/ipylab)
[![npm](https://img.shields.io/npm/v/ipylab.svg)](https://www.npmjs.com/package/ipylab)

Control JupyterLab from Python.

The goal is to provide access to most of the JupyterLab environment from the Python kernel. For example:

- Adding widgets to the main area `DockPanel`, left, right or top area
- Build more advanced interfaces leveraging `SplitPanel`, `Toolbar` and other Lumino widgets
- Launch arbitrary commands (new terminal, change theme, open file and so on)
- Open a workspace with a specific layout
- Listen to JupyterLab signals (notebook opened, console closed) and trigger Python callbacks

## Try it online

Try it in your browser with Binder:

[![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/jtpio/ipylab/main?urlpath=lab/tree/examples/widgets.ipynb)

Or with [JupyterLite](https://github.com/jupyterlite/jupyterlite):

[![JupyterLite](https://jupyterlite.rtfd.io/en/latest/_static/badge-launch.svg)](https://ipylab.readthedocs.io/en/latest/lite/lab)

## Examples

### Add Jupyter Widgets to the JupyterLab interface

![widgets-panels](https://user-images.githubusercontent.com/591645/80025074-59104280-84e0-11ea-9766-0cb49cba285a.gif)

### Execute Commands

![command-registry](https://user-images.githubusercontent.com/591645/80026017-beb0fe80-84e1-11ea-842d-fa3bf5bc4a9b.gif)

### Custom Python Commands and Command Palette

![custom-commands](https://user-images.githubusercontent.com/591645/80026023-c1135880-84e1-11ea-9e83-fdb739659357.gif)

### Build small applications

![ipytree-example](https://user-images.githubusercontent.com/591645/80026006-b8bb1d80-84e1-11ea-87cc-86495186b938.gif)

## Installation

You can install using `pip`:

```bash
pip install ipylab
```

## Dependencies

The following dependencies have patched versions specified in the `'pyproject.toml'` file to enable better functionality.

| Name                           | Pull request                                                                                                                        | Status         | Modification                                                                                                                              |
| ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------- | -------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| ipywidgets, jupyterlab-widgets | [#3922](https://github.com/jupyter-widgets/ipywidgets/pull/3922) + [#3921](https://github.com/jupyter-widgets/ipywidgets/pull/3921) | Pending review | Provides for widgets comms without needing a notebook or console to be open. Plus fixes for proper garbage collection and widget tooltips |
|                                |

## Examples

Example files can be downloaded directly from github [here](https://github.com/jtpio/ipylab/tree/main/examples).

## Under the hood

`ipylab` can be seen as a proxy from Python to JupyterLab over Jupyter Widgets:

![ipylab-diagram](./docs/ipylab.png)

## Development

The development environment is provided by [uv](https://docs.astral.sh/uv/).

### Installation from source

If you are working on a pull request, [make a fork] of the project and install from your fork.

```shell
git clone <repository>
cd ipylab
uv venv -p python@311 # or whichever environment you are targeting.
uv sync
# Activate the uv environment
```

### Frontend (Typescript/Javascript)

```bash
# Activate the uv environment

# compile the extension
jlpm clean
jlpm build

# **Frontend/typescript development only** link the extension files
jupyter-builder develop . --overwrite

# At this point you can run and debug. vscode configs are provided for Firefox and Chrome.
# "Debug Ipylab with Firefox | Chrome"
```

```bash
# pre-commit (optional)
pre-commit run

# or, to install the git hook
pre-commit install

# Use jlpm script to lint the JS
jlpm lint
#or
jlpm lint:check

```

!!! note

    If you're developing the fronted on Windows you need to [enable developer mode](https://learn.microsoft.com/en-us/windows/apps/get-started/enable-your-device-for-development#activate-developer-mode) for symlinks to work.

    [see also](https://discuss.python.org/t/add-os-junction-pathlib-path-junction-to/50394).

### Serve Jupyterlite locally

```bash
# Load python packages (do once)
uv sync --group docs

# Load node packages (do once)
jlpm

# Clean if required
jlpm clean:all

jlpm jupyterlite:serve
```

### Upgrade files

=== "Python files"

    ```bash
    uv sync -U
    ```

=== "Frontend"

    TODO

### Type checking

Type checking is performed using [basedpyright](https://docs.basedpyright.com/).

```bash
uvx basedpyright@1.39.6
```

### VS code debugging

A config file is included to debug `ipylab` with Firefox or Chrome.

## Related projects

There are a couple of projects that also enable interacting with the JupyterLab environment from Python notebooks:

- [wxyz](https://github.com/deathbeds/wxyz): experimental widgets (including `DockPanel`)
- [jupyterlab-sidecar](https://github.com/jupyter-widgets/jupyterlab-sidecar): add widgets to the JupyterLab right area
- [jupyterlab_commands](https://github.com/timkpaine/jupyterlab_commands): add arbitrary Python commands to the jupyterlab command palette
