# iriscc

`iriscc` is a collection of hydrological modelling workflows, notebooks, and demonstrators built around the HydroMT ecosystem. The repository contains example setups and exploratory notebooks for model preparation, execution, and visualization using tools such as HydroMT, SFINCS, FIAT, and D-HYDRO.

The notebooks in this repository serve both as documentation and executable examples of the workflows.

## Environment setup

This project uses Pixi to manage dependencies and development tasks.

### Install Pixi

Pixi can be installed using the official installer.

Linux / macOS:

```
curl -fsSL https://pixi.sh/install.sh | bash
```

Windows (PowerShell):

```
powershell -ExecutionPolicy ByPass -c "irm https://pixi.sh/install.ps1 | iex"
```

After installation, restart your shell so the `pixi` command becomes available.

### Install the project environment

Clone the repository and install the environment:

```
git clone https://github.com/Deltares-research/iriscc.git
cd iriscc
pixi install
```

Pixi will create a reproducible environment based on the `pyproject.toml` and `pixi.lock` files.

## Running notebooks

All notebooks in the repository can be executed using the Pixi task:

```
pixi run run-notebooks
```

This runs every notebook in the repository and updates them with executed outputs.

## Cleaning notebook outputs

To remove outputs from all notebooks:

```
pixi run clean-notebooks
```

This clears cell outputs and execution counters to keep notebooks clean for version control.
