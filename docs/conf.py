extensions = ["myst_parser", "jupyterlite_sphinx"]

jupyterlite_config = "jupyter_lite_config.json"
jupyterlite_dir = "."
jupyterlite_contents = ["./files/"]

master_doc = "index"
source_suffix = ".md"

# General information about the project.
project = "ipylab"
author = "ipylab contributors"

exclude_patterns = []
highlight_language = "python"
pygments_style = "sphinx"

html_theme = "pydata_sphinx_theme"
