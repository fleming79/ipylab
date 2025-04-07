# ipylab

![Github Actions Status](https://github.com/jtpio/ipylab/workflows/Build/badge.svg)
[![JupyterLite](https://jupyterlite.rtfd.io/en/latest/_static/badge-launch.svg)](https://ipylab.readthedocs.io/en/latest/lite/lab)
[![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/jtpio/ipylab/main?urlpath=lab/tree/examples/widgets.ipynb)
[![Conda Version](https://img.shields.io/conda/vn/conda-forge/ipylab.svg)](https://anaconda.org/conda-forge/ipylab)
[![pypi](https://img.shields.io/pypi/v/ipylab.svg)](https://pypi.python.org/pypi/ipylab)
[![npm](https://img.shields.io/npm/v/ipylab.svg)](https://www.npmjs.com/package/ipylab)

Control JupyterLab from Python notebooks.

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

### Compatibility with RetroLab

A subset of the features can be used in RetroLab:

![retrolab-example](https://user-images.githubusercontent.com/591645/141700044-3c39661a-8a9a-4e6b-a031-03724e0df25b.gif)

## Installation

You can install using `pip`:

```bash
pip install ipylab
```

Or with `mamba` / `conda`:

```bash
mamba install -c conda-forge ipylab
```

### Per kernel widget manager

The current behaviour of IpyWidgets requires a Notebook or Console to create the
Widget. Once the Notebook or Console Panel is closed, the widget comms is closed
making the widget unavailable.

This [Pull Request](https://github.com/jupyter-widgets/ipywidgets/pull/3922) modifies
the widget manager so widgets can be created without requiring a Notebook or Console
to be open.

Wheels in the `/pkg/` folder were built using this [source](https://github.com/fleming79/ipywidgets/tree/weakref-and-per-kernel-widget-manager)
combining [Per-kernel-widget-manager](https://github.com/jupyter-widgets/ipywidgets/pull/3922)
and [weakref](https://github.com/fleming79/ipywidgets/tree/weakref).

These versions enable:

- Widget restoration when the page is reloaded.
- Starting new kernels and opening widgets from those kernels.
- autostart plugins - Run code when Jupyterlab is started.
- Viewing widgets from kernels inside from other kernels.

```bash
pip install --no-binary --force-reinstall ipylab
```

## Running the examples locally

To try out the examples locally, the recommended way is to create a new environment with the dependencies:

```bash
# create a new conda environment
conda create -n ipylab-examples -c conda-forge jupyterlab ipylab ipytree bqplot ipywidgets numpy
conda activate ipylab-examples

# start JupyterLab
jupyter lab
```

## Under the hood

`ipylab` can be seen as a proxy from Python to JupyterLab over Jupyter Widgets:

![ipylab-diagram](./docs/ipylab.png)

## Development

```bash
# create a new conda environment
conda create -n ipylab -c conda-forge nodejs python=3.11 -y

# activate the environment
conda activate ipylab

# install the Python package
pip install -e .[dev,test]

# link the extension files
jupyter labextension develop . --overwrite

# compile the extension
jlpm clean
jlpm build

# pre-commit (optional)
pip install pre-commit
pre-commit run

# or, to install the git hook
pre-commit install

# Use jlpm script to lint the JS
jlpm lint
#or
jlpm lint:check

# Pyright

pip install pyright[nodejs]
pyright
```

### VS code debugging

A config file is included to debug ipylab with Firefox or Chrome.

## Related projects

There are a couple of projects that also enable interacting with the JupyterLab environment from Python notebooks:

- [wxyz](https://github.com/deathbeds/wxyz): experimental widgets (including `DockPanel`)
- [jupyterlab-sidecar](https://github.com/jupyter-widgets/jupyterlab-sidecar): add widgets to the JupyterLab right area
- [jupyterlab_commands](https://github.com/timkpaine/jupyterlab_commands): add arbitrary Python commands to the jupyterlab command palette
