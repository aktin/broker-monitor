"""
@AUTHOR=Wiliam Hoy (whoy@ukaachen.de)
@VERSION=1.5

Creates clinic error-rate heatmaps from CSV-based monitoring data.

This module contains:
- HeatMapDiagram: rendering and exporting a single heatmap
- HeatMapFactory: transforms raw monitoring data into heatmap-ready format
- ChartManager: loads clinic CSV files and coordinates heatmap generation
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from common import ConfluenceNodeMapper


class HeatMapDiagram:
    """
    Represents one concrete heatmap diagram. Can be shown and saved.

    Responsibilities:
    - store heatmap data
    - manage rendering configuration
    - build, save, show, and close the matplotlib figure
    """

    def __init__(self, data: pd.DataFrame, title: str | None = None):
        if not isinstance(data, pd.DataFrame):
            raise TypeError("data must be a pandas DataFrame")

        self.data = data.copy()
        self.title = title

        # render state
        self.figure: plt.Figure | None = None
        self.axis = None
        self.image = None

        # layout / labels
        self.figsize: tuple[float, float] = (12, 8)
        self.xlabel: str = ""
        self.ylabel: str = ""
        self.show_x_ticks: bool = True
        self.show_y_ticks: bool = True
        self.y_labels_right: bool = True

        # label sizes
        self.axis_label_size: int = 12
        self.tick_label_size: int = 10
        self.colorbar_label_size: int = 12
        self.colorbar_tick_label_size: int = 10

        # custom x ticks
        self._custom_xticks: list[int] | None = None
        self._custom_xticklabels: list[str] | None = None

        # colorbar
        self.show_colorbar = True
        self.colorbar_label: str = "Anzahl der täglichen Fehler"
        self.colorbar_ticks: list[float] | None = None
        self.colorbar_ticklabels: list[str] | None = None
        self.colorbar_location: str = "top"   # top / bottom / left / right
        self.colorbar_fraction: float = 0.04
        self.colorbar_pad: float = 0.02
        self.colorbar_shrink: float = 1.0

        # row separators
        self.row_separators_enabled: bool = False
        self.row_separator_width: float = 0.5
        self.row_separator_color: str = "black"

        # colormap
        self.cmap = None
        self.norm = None
        self._set_default_colormap()

    @classmethod
    def from_csv(cls, file_path: str | Path, title: str | None = None) -> "HeatMapDiagram":
        """
        Creates a HeatMapDiagram from a CSV file where:
        - first column is the row label / index
        - remaining columns are numeric heatmap values
        """
        df = pd.read_csv(file_path, header=None, index_col=0)
        df = df.apply(pd.to_numeric, errors="coerce")
        return cls(data=df, title=title)

    @classmethod
    def from_df(cls, df: pd.DataFrame, title: str | None = None) -> "HeatMapDiagram":
        """
        Creates a HeatMapDiagram from an existing DataFrame.

        Assumes:
        - DataFrame index is already the row label
        - DataFrame columns are the heatmap x-axis values
        """
        if not isinstance(df, pd.DataFrame):
            raise TypeError("df must be a pandas DataFrame")

        data = df.copy()
        data = data.apply(pd.to_numeric, errors="coerce")
        return cls(data=data, title=title)

    def _set_default_colormap(self) -> None:
        """
        Default discrete colormap:
        < 0   -> white
        0..5  -> blue
        5..10 -> yellow
        >=10  -> red
        """
        colors = ["white", "blue", "yellow", "red"]
        bounds = [-1e9, 0, 5, 10, 1e9]

        self.cmap = mcolors.ListedColormap(colors)
        self.norm = mcolors.BoundaryNorm(bounds, self.cmap.N)

        self.colorbar_ticks = [-5, 2.5, 7.5, 12]
        self.colorbar_ticklabels = ["< 0", "0–5", "5–10", "≥ 10"]

    def set_colormap(self, colors: list[str], bounds: list[float]) -> None:
        if len(bounds) != len(colors) + 1:
            raise ValueError("bounds must have exactly one more element than colors")

        self.cmap = mcolors.ListedColormap(colors)
        self.norm = mcolors.BoundaryNorm(bounds, self.cmap.N)

    def set_colorbar_visible(self, visible: bool):
        self.show_colorbar = visible

    def set_colorbar_labels(self, ticks: list[float], labels: list[str]) -> None:
        if len(ticks) != len(labels):
            raise ValueError("ticks and labels must have the same length")

        self.colorbar_ticks = list(ticks)
        self.colorbar_ticklabels = list(labels)

    def set_colorbar_location(self, location: str) -> None:
        valid_locations = {"top", "bottom", "left", "right"}
        if location not in valid_locations:
            raise ValueError(f"location must be one of {valid_locations}")
        self.colorbar_location = location

    def set_colorbar_size(
        self,
        fraction: float | None = None,
        pad: float | None = None,
        shrink: float | None = None,
    ) -> None:
        if fraction is not None:
            self.colorbar_fraction = fraction
        if pad is not None:
            self.colorbar_pad = pad
        if shrink is not None:
            self.colorbar_shrink = shrink

    def set_colorbar_size_from_height(
        self,
        cbar_height: float,
        ax_height: float,
        ratio: float = 0.6,
        shrink: float | None = None,
    ) -> None:
        """
        Approximates colorbar fraction and pad based on desired absolute heights.

        ax_height: heatmap axis height in inches
        cbar_height: total reserved colorbar section height in inches
        ratio: portion of cbar_height used by the bar itself
        """
        if ax_height <= 0:
            raise ValueError("ax_height must be > 0")
        if cbar_height <= 0:
            raise ValueError("cbar_height must be > 0")
        if not 0 < ratio < 1:
            raise ValueError("ratio must be between 0 and 1")

        total_height = ax_height + cbar_height
        self.colorbar_fraction = ratio * cbar_height / total_height
        self.colorbar_pad = (1 - ratio) * cbar_height / total_height

        if shrink is not None:
            self.colorbar_shrink = shrink

    def set_figure_size(self, width: float, height: float) -> None:
        self.figsize = (width, height)

    def set_axis_labels(self, xlabel: str | None = None, ylabel: str | None = None) -> None:
        if xlabel is not None:
            self.xlabel = xlabel
        if ylabel is not None:
            self.ylabel = ylabel

    def set_label_sizes(
        self,
        axis_label_size: int | None = None,
        tick_label_size: int | None = None,
        colorbar_label_size: int | None = None,
        colorbar_tick_label_size: int | None = None,
    ) -> None:
        if axis_label_size is not None:
            self.axis_label_size = axis_label_size
        if tick_label_size is not None:
            self.tick_label_size = tick_label_size
        if colorbar_label_size is not None:
            self.colorbar_label_size = colorbar_label_size
        if colorbar_tick_label_size is not None:
            self.colorbar_tick_label_size = colorbar_tick_label_size

    def set_title(self, title: str) -> None:
        self.title = title

    def set_xticks(self, positions, labels=None) -> None:
        self._custom_xticks = list(positions)
        self._custom_xticklabels = None if labels is None else list(labels)

    def set_tick_visibility(self, show_x_ticks: bool = True, show_y_ticks: bool = True) -> None:
        self.show_x_ticks = show_x_ticks
        self.show_y_ticks = show_y_ticks

    def set_y_labels_right(self, enabled: bool = True) -> None:
        self.y_labels_right = enabled

    def enable_row_separators(self, color: str = "black", width: float = 0.5) -> None:
        self.row_separators_enabled = True
        self.row_separator_color = color
        self.row_separator_width = width

    def rename_index(self, rename_function: Callable[[object], str]) -> None:
        self.data.index = [rename_function(idx) for idx in self.data.index]

    def build(self) -> None:
        self.close()

        self.figure, self.axis = plt.subplots(figsize=self.figsize)
        self.image = self.axis.imshow(
            self.data,
            cmap=self.cmap,
            norm=self.norm,
            aspect="auto",
        )

        self._apply_axis_formatting()
        self._draw_row_separators()
        if self.show_colorbar:
            self._add_colorbar()

        self.figure.tight_layout()

    def _apply_axis_formatting(self) -> None:
        if self.axis is None:
            raise RuntimeError("Axis does not exist. Call build() first")

        self.axis.tick_params(axis="both", labelsize=self.tick_label_size)

        if self.y_labels_right:
            self.axis.yaxis.tick_right()
            self.axis.yaxis.set_label_position("right")

        if self.show_y_ticks:
            self.axis.set_yticks(range(len(self.data.index)))
            self.axis.set_yticklabels(list(self.data.index))
        else:
            self.axis.set_yticks([])

        if self.show_x_ticks:
            if self._custom_xticks is not None:
                self.axis.set_xticks(self._custom_xticks)
                if self._custom_xticklabels is not None:
                    self.axis.set_xticklabels(self._custom_xticklabels)
            else:
                self.axis.set_xticks(range(len(self.data.columns)))
                self.axis.set_xticklabels([str(col) for col in self.data.columns])
        else:
            self.axis.set_xticks([])

        self.axis.set_xlabel(self.xlabel, fontsize=self.axis_label_size)
        self.axis.set_ylabel(self.ylabel, fontsize=self.axis_label_size)

        if self.title:
            self.axis.set_title(self.title)

    def _draw_row_separators(self) -> None:
        if not self.row_separators_enabled:
            return

        if self.axis is None:
            raise RuntimeError("Axis does not exist. Call build() first")

        n_rows, n_cols = self.data.shape

        self.axis.hlines(
            y=[i - 0.5 for i in range(1, n_rows)],
            xmin=-0.5,
            xmax=n_cols - 0.5,
            colors=self.row_separator_color,
            linewidth=self.row_separator_width,
        )

    def _add_colorbar(self) -> None:
        if self.figure is None or self.axis is None or self.image is None:
            raise RuntimeError("Figure not built yet. Call build() first")

        orientation = "horizontal" if self.colorbar_location in {"top", "bottom"} else "vertical"

        cbar = self.figure.colorbar(
            self.image,
            ax=self.axis,
            location=self.colorbar_location,
            orientation=orientation,
            ticks=self.colorbar_ticks,
            fraction=self.colorbar_fraction,
            pad=self.colorbar_pad,
            shrink=self.colorbar_shrink,
        )

        cbar.set_label(self.colorbar_label, fontsize=self.colorbar_label_size)
        cbar.ax.tick_params(labelsize=self.colorbar_tick_label_size)

        if self.colorbar_ticklabels is not None:
            if orientation == "vertical":
                cbar.ax.set_yticklabels(self.colorbar_ticklabels)
            else:
                cbar.ax.set_xticklabels(self.colorbar_ticklabels)

    def get_colorbar_total_height_inch(self) -> float:
        if self.figure is None or self.axis is None:
            raise RuntimeError("Figure not built yet. Call build() first")

        fig_height = self.figure.get_size_inches()[1]
        axis_height = self.axis.get_position().height * fig_height

        cbar_height = self.colorbar_fraction * axis_height
        pad_height = self.colorbar_pad * axis_height

        return cbar_height + pad_height

    def save(self, file_path: str | Path, dpi: int = 300) -> None:
        if file_path is None:
            raise ValueError("file_path must not be None")

        if self.figure is None:
            self.build()

        self.figure.savefig(file_path, dpi=dpi, bbox_inches="tight")

    def show(self) -> None:
        if self.figure is None:
            self.build()
        plt.show()

    def close(self) -> None:
        if self.figure is not None:
            plt.close(self.figure)
            self.figure = None
            self.axis = None
            self.image = None


class HeatMapFactory:
    """
    Prepares heatmap data and configures a HeatMapDiagram.

    Responsibilities:
    - transform raw clinic error data into heatmap-ready format
    - compute clinic sorting scores
    - configure the final diagram
    """

    def generate_diagram(
        self,
        df: pd.DataFrame,
        save_path: str | Path | None = None,
        timeframe: int = 30,
        row_height: float = 0.2,
        figure_width: float = 14,
        colorbar_height: float = None,
        show: bool = False,
    ) -> HeatMapDiagram:
        heat = self._prepare_heatmap_data(df, timeframe)

        diagram = HeatMapDiagram.from_df(
            heat,
            title=f"Fehlerraten - letzte {timeframe} Tage; Sortiert nach relativer Änderung der letzten Tage",
        )
        axis_height = heat.shape[0] * row_height
        figure_height = axis_height
        if colorbar_height:
            figure_height += colorbar_height
            diagram.set_colorbar_location("top")
            diagram.set_colorbar_size_from_height(
                cbar_height=colorbar_height,
                ax_height=axis_height,
                ratio=0.3,
            )
        else:
            diagram.set_colorbar_visible(False)
        diagram.set_figure_size(figure_width, figure_height)
        diagram.set_label_sizes(
            axis_label_size=14,
            tick_label_size=max(int(6 * row_height * 10), 1),
            colorbar_label_size=12,
            colorbar_tick_label_size=9,
        )
        diagram.enable_row_separators(color="darkgray", width=0.5)

        x_label_ids = np.where(heat.columns.day % 5 == 0)[0]
        x_labels = heat.columns.strftime("%d-%m")[x_label_ids]
        diagram.set_xticks(x_label_ids, x_labels)

        if save_path is not None:
            diagram.save(save_path)

        if show:
            diagram.show()

        return diagram

    def _prepare_heatmap_data(self, df: pd.DataFrame, timeframe: int) -> pd.DataFrame:
        required_columns = {"clinic_name", "date", "daily_error_rate"}
        missing = required_columns - set(df.columns)
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        scores = self._get_clinic_scores(df)

        pivoted = (
            df[["clinic_name", "date", "daily_error_rate"]]
            .pivot(index="date", columns="clinic_name", values="daily_error_rate")
            .sort_index()
        )

        max_date = pivoted.index.max()
        cutoff = max_date - pd.Timedelta(days=timeframe)
        windowed = pivoted.loc[pivoted.index >= cutoff]

        heat = windowed.T
        heat.index = heat.index.rename("clinic_name")

        heat_sorted = (
            heat.merge(scores, left_index=True, right_index=True, how="left")
            .sort_values(by="score", ascending=True)
            .drop(columns=["score"])
        )

        heat_sorted.columns = pd.to_datetime(heat_sorted.columns)
        heat_sorted = heat_sorted.apply(pd.to_numeric, errors="coerce")

        return heat_sorted

    def _get_clinic_scores(self, df: pd.DataFrame, short_pct: float = 0.2) -> pd.DataFrame:
        scores = df.groupby("clinic_name")["daily_error_rate"].agg(
            lambda values: self._calc_likelihood_by_errors(values.to_numpy(), short_pct)
        )
        return scores.to_frame(name="score")

    def _calc_likelihood_by_errors(self, values: np.ndarray, short_pct: float) -> float:
        """
        Calculates a score for comparing the recent error trend to the full history.
        Higher similarity means the recent part behaves more like the full series.
        """
        eps = np.finfo(float).eps

        def fit_normal(arr: np.ndarray) -> tuple[float, float]:
            return float(np.mean(arr)), float(np.std(arr))

        def normal_pdf(x, mu, sigma):
            sigma = max(abs(float(sigma)), eps)
            return (1 / (sigma * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x - mu) / sigma) ** 2)

        def overlap_between_normals(mu1, sigma1, mu2, sigma2, num_points: int = 10_000) -> float:
            if np.isclose(sigma1, 0.0) and np.isclose(sigma2, 0.0):
                return 1.0 if np.isclose(mu1, mu2) else 0.0

            sigma1 = max(abs(float(sigma1)), eps)
            sigma2 = max(abs(float(sigma2)), eps)

            min_x = min(mu1 - 4 * sigma1, mu2 - 4 * sigma2)
            max_x = max(mu1 + 4 * sigma1, mu2 + 4 * sigma2)

            x = np.linspace(min_x, max_x, num_points)
            pdf1 = normal_pdf(x, mu1, sigma1)
            pdf2 = normal_pdf(x, mu2, sigma2)

            overlap = np.trapezoid(np.minimum(pdf1, pdf2), x)
            area1 = np.trapezoid(pdf1, x)
            area2 = np.trapezoid(pdf2, x)

            difference = area1 + area2 - (2 * overlap)
            similarity = 1 - difference
            return float(similarity)

        short_size = max(int(values.shape[0] * short_pct), 1)

        mu_full, sig_full = fit_normal(values)
        mean_scale = mu_full if not np.isclose(mu_full, 0.0) else 1.0

        error_full = ((values - mu_full) / mean_scale) ** 2
        error_short = error_full[-short_size:]

        mu_error_full, sig_error_full = fit_normal(error_full)
        if np.isclose(sig_error_full, 0.0):
            return 1.0

        z_full = (error_full - mu_error_full) / sig_error_full
        z_short = (error_short - mu_error_full) / sig_error_full

        mu_z_full, sig_z_full = fit_normal(z_full)
        mu_z_short, sig_z_short = fit_normal(z_short)

        return overlap_between_normals(mu_z_full, sig_z_full, mu_z_short, sig_z_short)


class ChartManager:
    """
    Collects raw clinic CSV files and generates the final heatmap.
    """

    def __init__(self, mapper: ConfluenceNodeMapper, csv_paths: list[str] | None = None):
        self.mapper = mapper
        self.csv_paths = csv_paths if csv_paths is not None else []

    def generate_heat(self, save_path: str | Path, show: bool = False) -> None:
        heatmap_factory = HeatMapFactory()
        data_frames: list[pd.DataFrame] = []

        for path in self.csv_paths:
            clinic_df = pd.read_csv(path, sep=";").convert_dtypes()

            clinic_id = self._get_clinic_num(path)
            clinic_name = self.mapper.get_node_value_from_mapping_dict(clinic_id, "COMMON_NAME")

            clinic_df["clinic_id"] = clinic_id
            clinic_df["clinic_name"] = clinic_name

            data_frames.append(clinic_df)

        if not data_frames:
            raise ValueError("No CSV files available to generate the heatmap")

        data = pd.concat(data_frames, ignore_index=True)
        data = data[["date", "clinic_id", "clinic_name", "daily_error_rate"]]
        data = self._normalize_column_types(data)
        data = data.fillna(-10)

        diagram = heatmap_factory.generate_diagram(
            df=data,
            save_path=save_path,
            show=show,
        )

        if not show:
            diagram.close()

    def _get_clinic_num(self, path: str | Path) -> str:
        return Path(path).name.split("_")[0]

    @staticmethod
    def _normalize_column_types(data: pd.DataFrame) -> pd.DataFrame:
        result = data.copy()

        for col in result.columns:
            numeric_converted = pd.to_numeric(result[col], errors="coerce")
            if numeric_converted.notna().sum() > 0:
                result[col] = numeric_converted
                continue

            datetime_converted = pd.to_datetime(result[col], errors="coerce", utc=True)
            if datetime_converted.notna().sum() > 0:
                result[col] = datetime_converted.dt.normalize()

        return result
