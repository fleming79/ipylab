# ipylab

<!-- ![Github Actions Status](https://github.com/jtpio/ipylab/workflows/Build/badge.svg)
[![pypi](https://img.shields.io/pypi/v/ipylab.svg)](https://pypi.python.org/pypi/ipylab)
[![npm](https://img.shields.io/npm/v/ipylab.svg)](https://www.npmjs.com/package/ipylab) -->

Control JupyterLab from Python.

The goal is to provide access to most of the JupyterLab environment from the Python kernel. For example:

- Adding widgets to the main area `DockPanel`, left, right or top area
- Build more advanced interfaces leveraging `SplitPanel`, `Toolbar` and other Lumino widgets
- Launch arbitrary commands (new terminal, change theme, open file and so on)
- Open a workspace with a specific layout
- Listen to JupyterLab signals (notebook opened, console closed) and trigger Python callbacks


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

Use pip to install from source.

Download [source](https://github.com/fleming79/ipylab/releases/download/v2.0.0b5/ipylab-2.0.0b5.tar.gz).

``` bash
pip install ipylab-2.0.0b5.tar.gz # Update version as required.
```


## Dependencies

The following dependencies are provided as wheels in the pkg directory which include patches to
improved the functionality.

| Name                                               | Pull request                                            | Status                      | Modification        |
| -------------------------------------------------- | ------------------------------------------------------- | --------------------------- | ------------------- |
| traitlets                                          | [#918](https://github.com/ipython/traitlets/pull/918)   | Accepted - pending release  | Improved type hints |
| ipywidgets, jupyterlab-widgets, widgetsnbextension | [#3922](https://github.com/jupyter-widgets/ipywidgets/pull/3922) + [#3921](https://github.com/jupyter-widgets/ipywidgets/pull/3921) | Pending review | Provides for widgets comms without needing a notebook or console to be open. Plus fixes for proper garbage collection and widget tooltips |
| jupyter_client | [#1064](https://github.com/jupyter/jupyter_client/pull/1064)  | Pending review | Faster message serialization |
| async_kernel | [Not a PR](https://github.com/fleming79/ipykernel/tree/async) | Awaiting feedback from [Ipython / Jupyter developers](https://github.com/ipython/ipykernel/pull/1384) | This kernel is native async. Importantly, execute_requests are run in tasks enabling shell messages to pass whilst execute_requests are being performed. This makes it possible to await async methods in ipylab that rely on custom shell messages.  |

Use the source distribution to ensure the dependencies are bundled.

``` bash
uv build --sdist
```

## Running the examples locally

To try out the examples locally you can install with pip:

```bash

# for examples
pip install ipylab[examples] https://github.com/fleming79/ipylab/releases/download/v2.0.0b5/ipylab-2.0.0b5.tar.gz

ipylab
```

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
# Activate the environment
```

### Frontend (Typescript/Javascript)

If you are making changes to the you also need to have nodejs available. Fortunately
[nodejs-wheel](https://pypi.org/project/nodejs-wheel/) provides a wheel for this. It can be installed using:

```bash
# Build / install - may take a long time (~5min) initially
uv sync

# Activate the environment

# **Frontend/typescript development only** link the extension files
jupyter labextension develop . --overwrite

# compile the extension
jlpm clean
jlpm build

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
basedpyright
```

### VS code debugging

A config file is included to debug `ipylab` with Firefox or Chrome.

## Related projects

There are a couple of projects that also enable interacting with the JupyterLab environment from Python notebooks:

- [wxyz](https://github.com/deathbeds/wxyz): experimental widgets (including `DockPanel`)
- [jupyterlab-sidecar](https://github.com/jupyter-widgets/jupyterlab-sidecar): add widgets to the JupyterLab right area
- [jupyterlab_commands](https://github.com/timkpaine/jupyterlab_commands): add arbitrary Python commands to the jupyterlab command palette
