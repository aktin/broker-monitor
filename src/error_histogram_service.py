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

from src.common import ConfluenceNodeMapper


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

# """
# @AUTHOR=Wiliam Hoy (whoy@ukaachen.de)
# @VERSION=1.4
# """
# from src.common import ConfluenceNodeMapper
# import pandas as pd
# import matplotlib.pyplot as plt
# import matplotlib.colors as mcolors
# import numpy as np
#
#
# class HeatMapDiagram:
#     """
#     Represents one concrete heatmap diagram.
#
#     Responsibilities:
#     - load/store the heatmap data
#     - manage colormap and thresholds
#     - create the matplotlib figure
#     - save or show the diagram
#
#     Designed to be extendable, so more style or preprocessing methods
#     can be added later without changing the external usage too much.
#     """
#
#     def __init__(self, data: pd.DataFrame, title: str | None = None):
#         self.data = data.copy()
#         self.title = title
#
#         self.figure = None
#         self.axis = None
#         self.image = None
#
#         self.figsize = (12, 8)
#         self.xlabel = ""
#         self.ylabel = ""
#         self.show_x_ticks = True
#         self.show_y_ticks = True
#         self.colorbar_label = "Anzahl der täglichen Fehler"
#         self.axis_label_size = 12
#         self.tick_label_size = 10
#         self.colorbar_label_size = 12
#         self.colorbar_tick_label_size = 10
#         self._custom_xticks = None
#         self._custom_xticklabels = None
#
#         self.cmap = None
#         self.norm = None
#         self.colorbar_ticks = None
#         self.colorbar_ticklabels = None
#         self.y_labels_right = True
#         self.colorbar_location = "top"  # top/bottom/left/right
#         self.colorbar_fraction = 0.04  # thickness
#         self.colorbar_pad = 0.02  # distance from heatmap
#         self.colorbar_shrink = 1.0  # vertical scaling
#
#         self.row_separators = False
#         self.row_separator_width = 0.5
#         self.row_separator_color = "black"
#
#         self._set_default_colormap()
#
#     @classmethod
#     def from_csv(cls, file_path: str, title: str | None = None) -> "HeatMapDiagram":
#         """
#         Creates a HeatMapDiagram from a CSV file where:
#         - first column is the row label / index
#         - remaining columns are numeric heatmap values
#         """
#         df = pd.read_csv(file_path, header=None, index_col=0)
#         df = df.apply(pd.to_numeric, errors="coerce")
#         return cls(data=df, title=title)
#
#     @classmethod
#     def from_df(cls, df: pd.DataFrame, title: str | None = None) -> "HeatMapDiagram":
#         """
#         Creates a HeatMapDiagram from an existing pandas DataFrame.
#
#         The DataFrame index will be used as row labels and the columns
#         will represent the heatamap data points.
#         """
#
#         if not isinstance(df, pd.DataFrame):
#             raise TypeError("df must be a pandas DataFrame")
#
#         # ensure numeric data
#         data = df.copy()
#         df.index = df.iloc[:, 0]  # first column becomes index
#         df = df.iloc[:, 1:]  # remove first column
#         data = data.apply(pd.to_numeric, errors="coerce")
#
#         return cls(data=data, title=title)
#
#     def _set_default_colormap(self) -> None:
#         """
#         Default discrete colormap:
#         < 0   -> white
#         0..5  -> blue
#         5..10 -> yellow
#         >=10  -> red
#         """
#         colors = ["white", "blue", "yellow", "red"]
#         bounds = [-1e9, 0, 5, 10, 1e9]
#
#         self.cmap = mcolors.ListedColormap(colors)
#         self.norm = mcolors.BoundaryNorm(bounds, self.cmap.N)
#
#         self.colorbar_ticks = [-5, 2.5, 7.5, 12]
#         self.colorbar_ticklabels = ["< 0", "0–5", "5–10", "≥ 10"]
#
#     def set_colormap(self, colors: list[str], bounds: list[float]) -> None:
#         """
#         Sets a custom discrete colormap.
#
#         Example:
#             colors = ["white", "blue", "yellow", "red"]
#             bounds = [-1e9, 0, 5, 10, 1e9]
#         """
#         if len(bounds) != len(colors) + 1:
#             raise ValueError("bounds must have exactly one more element than colors.")
#
#         self.cmap = mcolors.ListedColormap(colors)
#         self.norm = mcolors.BoundaryNorm(bounds, self.cmap.N)
#
#         self.colorbar_ticks = None
#         self.colorbar_ticklabels = None
#
#     def set_colorbar_size(self, fraction: float = None, pad: float = None, shrink: float = None):
#         if fraction is not None:
#             self.colorbar_fraction = fraction
#         if pad is not None:
#             self.colorbar_pad = pad
#         if shrink is not None:
#             self.colorbar_shrink = shrink
#
#     def set_colorbar_size_from_height(self, cbar_height: float, ax_height: float, ratio: float = 0.6, shrink: float = None):
#         """
#         ax_height: heigth of the heat map, not total size of figure
#         """
#         fig_height = ax_height + cbar_height
#         fraction = ratio * cbar_height / fig_height
#         pad = (1 - ratio) * cbar_height / fig_height
#
#         if fraction is not None:
#             self.colorbar_fraction = fraction
#         if pad is not None:
#             self.colorbar_pad = pad
#         if shrink is not None:
#             self.colorbar_shrink = shrink
#
#     def set_colorbar_location(self, location: str):
#         """
#         location: 'right', 'left', 'top', 'bottom'
#         """
#         self.colorbar_location = location
#
#     def set_colorbar_labels(self, ticks: list[float], labels: list[str]) -> None:
#         if len(ticks) != len(labels):
#             raise ValueError("ticks and labels must have the same length.")
#         self.colorbar_ticks = ticks
#         self.colorbar_ticklabels = labels
#
#     def set_figure_size(self, width: float, height: float) -> None:
#         self.figsize = (width, height)
#
#     def set_axis_labels(self, xlabel: str | None = None, ylabel: str | None = None) -> None:
#         if xlabel is not None:
#             self.xlabel = xlabel
#         if ylabel is not None:
#             self.ylabel = ylabel
#
#     def set_label_sizes(
#             self,
#             axis_label_size: int = None,
#             tick_label_size: int = None,
#             colorbar_label_size: int = None,
#             colorbar_tick_label_size: int = None
#     ):
#         if axis_label_size is not None:
#             self.axis_label_size = axis_label_size
#         if tick_label_size is not None:
#             self.tick_label_size = tick_label_size
#         if colorbar_label_size is not None:
#             self.colorbar_label_size = colorbar_label_size
#         if colorbar_tick_label_size is not None:
#             self.colorbar_tick_label_size = colorbar_tick_label_size
#
#     def set_title(self, title: str) -> None:
#         self.title = title
#
#     def set_xticks(self, positions, labels):
#         self._custom_xticks = positions
#         self._custom_xticklabels = labels
#
#     def set_tick_visibility(self, show_x_ticks: bool = True, show_y_ticks: bool = True) -> None:
#         self.show_x_ticks = show_x_ticks
#         self.show_y_ticks = show_y_ticks
#
#     def enable_row_separators(self, color="black", width=0.5):
#         self.row_separators = True
#         self.row_separator_color = color
#         self.row_separator_width = width
#
#     def _draw_row_separators(self):
#         if not self.row_separators:
#             return
#
#         n_rows = self.data.shape[0]
#         n_cols = self.data.shape[1]
#
#         self.axis.hlines(
#             y=[i - 0.5 for i in range(1, n_rows)],
#             xmin=-0.5,
#             xmax=n_cols - 0.5,
#             colors=self.row_separator_color,
#             linewidth=self.row_separator_width
#         )
#
#     def rename_index(self, rename_function) -> None:
#         """
#         Applies a renaming function to the row labels.
#
#         Example:
#             diagram.rename_index(lambda x: x.split('] ', 1)[1] if '] ' in x else x)
#         """
#         self.data.index = [rename_function(idx) for idx in self.data.index]
#
#     def build(self) -> None:
#         """
#         Creates the matplotlib figure and axis and draws the heatmap.
#         """
#         self.figure, self.axis = plt.subplots(figsize=self.figsize)
#
#         self.image = self.axis.imshow(
#             self.data,
#             cmap=self.cmap,
#             norm=self.norm,
#             aspect="auto"
#         )
#
#         self._apply_axis_formatting()
#         self._draw_row_separators()
#         self._add_colorbar()
#
#         self.figure.tight_layout()
#
#     def set_y_labels_right(self, enabled: bool = True):
#         self.y_labels_right = enabled
#
#     def _apply_axis_formatting(self) -> None:
#         if self.axis is None:
#             raise RuntimeError("Axis does not exist. Call build() first.")
#
#         self.axis.tick_params(axis="both", labelsize=self.tick_label_size)
#
#         if self.y_labels_right:
#             self.axis.yaxis.tick_right()
#             self.axis.yaxis.set_label_position("right")
#
#         if self.show_y_ticks:
#             self.axis.set_yticks(range(len(self.data.index)))
#             self.axis.set_yticklabels(list(self.data.index))
#         else:
#             self.axis.set_yticks([])
#
#         if self.show_x_ticks:
#             if self._custom_xticks is not None:
#                 self.axis.set_xticks(list(self._custom_xticks))
#                 if self._custom_xticklabels is not None:
#                     self.axis.set_xticklabels(list(self._custom_xticklabels))
#             else:
#                 self.axis.set_xticks(range(len(self.data.columns)))
#                 self.axis.set_xticklabels(list(self.data.columns))
#         else:
#             self.axis.set_xticks([])
#
#         self.axis.set_xlabel(self.xlabel, fontsize=self.axis_label_size)
#         self.axis.set_ylabel(self.ylabel, fontsize=self.axis_label_size)
#
#         if self.title:
#             self.axis.set_title(self.title)
#
#     def _add_colorbar(self) -> None:
#         if self.figure is None or self.axis is None or self.image is None:
#             raise RuntimeError("Figure not built yet. Call build() first.")
#
#         orientation = "vertical"
#         if self.colorbar_location in ("top", "bottom"):
#             orientation = "horizontal"
#
#         cbar = self.figure.colorbar(
#             self.image,
#             ax=self.axis,
#             location=self.colorbar_location,
#             orientation=orientation,
#             ticks=self.colorbar_ticks,
#             fraction=self.colorbar_fraction,
#             pad=self.colorbar_pad,
#             shrink=self.colorbar_shrink
#         )
#
#         if self.colorbar_ticklabels is not None:
#             if orientation == "vertical":
#                 cbar.ax.set_yticklabels(self.colorbar_ticklabels, fontsize=self.colorbar_tick_label_size)
#             else:
#                 cbar.ax.set_xticklabels(self.colorbar_ticklabels, fontsize=self.colorbar_tick_label_size)
#
#         cbar.set_label(self.colorbar_label)
#
#     def get_colorbar_total_height_inch(self):
#         fig_height = self.figure.get_size_inches()[1]
#         axis_height = self.axis.get_position().height * fig_height
#
#         cbar_height = self.colorbar_fraction * axis_height
#         pad_height = self.colorbar_pad * axis_height
#
#         return cbar_height + pad_height
#
#     def save(self, file_path: str, dpi: int = 300) -> None:
#         """
#         Saves the current diagram. If it has not been built yet, build it first.
#         """
#         if self.figure is None:
#             self.build()
#
#         self.figure.savefig(file_path, dpi=dpi, bbox_inches="tight")
#
#     def show(self) -> None:
#         """
#         Displays the current diagram. If it has not been built yet, build it first.
#         """
#         if self.figure is None:
#             self.build()
#
#         plt.show()
#
#     def close(self) -> None:
#         """
#         Closes the figure to free resources.
#         """
#         if self.figure is not None:
#             plt.close(self.figure)
#             self.figure = None
#             self.axis = None
#             self.image = None
#
# class HeatMapFactory:
#     """Generates a Heatmap using pandas DataFrame data. Prepares data, styling of diagram and saves it. """
#     def __init__(self, c_bar_height = 0.15, c_bar_gap = 1, free_width = 2):
#         self.c_bar_height = c_bar_height
#         self.c_bar_gap = c_bar_gap
#         self.free_width = free_width
#
#     def generate_diagram(self, df: pd.DataFrame, save_path: str = None, timeframe=30, row_height=0.2, width=10, cb_height: float=1.5):
#         """
#         row_height: each rows height in inch
#         """
#         heat = self._prepare_heatmap_data(df, timeframe)
#         ax_height = heat.shape[0] * row_height
#         fig_height = ax_height + cb_height
#
#         diagram = HeatMapDiagram.from_df(heat, title=f"Fehlerraten - letzte {timeframe} Tage")
#         diagram.set_axis_labels(xlabel="Datum", ylabel="Klinik")
#         diagram.set_figure_size(14, fig_height)
#         diagram.set_colorbar_size_from_height(
#             cbar_height=cb_height,
#             ax_height=ax_height,
#             ratio=0.3
#         )
#         diagram.set_colorbar_location("top")
#         diagram.set_label_sizes(
#             axis_label_size=14,
#             tick_label_size=int(6*row_height*10),
#             colorbar_label_size=12,
#             colorbar_tick_label_size=9
#         )
#         diagram.enable_row_separators(color="gray", width=0.3)
#         x_label_ids = np.where(heat.columns.day % 5 == 0)[0]
#         diagram.set_xticks(x_label_ids, heat.columns.strftime("%d-%m")[x_label_ids])
#         diagram.save(save_path)
#         diagram.show()
#         diagram.close()
#
#
#     def _prepare_heatmap_data(self, df: pd.DataFrame, timeframe: int) -> pd.DataFrame:
#         scores = self._get_clinic_scores(df)
#         pivoted = df[['clinic_name', 'date', 'daily_error_rate']].pivot(
#             index='date', columns='clinic_name', values='daily_error_rate'
#         ).reset_index()
#         max_date = pivoted.date.max()
#         cutoff = max_date - pd.Timedelta(days=timeframe)
#         windowed = pivoted.loc[pivoted.date >= cutoff].sort_values('date', ascending=True)
#         heat = windowed.T
#         heat.columns = heat.iloc[0].infer_objects()
#         heat = heat.iloc[1:]    # fix header row
#         heat.index = heat.index.rename('clinic_name')
#         heat_sorted = (
#             pd.merge(left=heat, left_on="clinic_name", right=scores, right_on="clinic_name", how="left")
#             .sort_values(by="score", ascending=True)
#             .drop(columns=['score'])
#         )
#         heat_sorted.columns = pd.to_datetime(heat_sorted.columns)
#         heat_sorted = heat_sorted.apply(pd.to_numeric, errors='coerce')
#         return heat_sorted
#
#     def _get_clinic_scores(self, df: pd.DataFrame, short_pct=0.2) -> pd.DataFrame:
#         scores = df.groupby(by='clinic_name')['daily_error_rate'].agg(lambda x:
#                     self._calc_likelihood_by_errors(x, short_pct)
#                  )
#         score_df = scores.to_frame().rename(columns={'daily_error_rate': 'score'})
#         return score_df
#
#
#     def _calc_likelihood_by_errors(self, X_full: np.ndarray, short_pct) -> float:
#         """Calculates a score metric for comparing relative error trend of a dataset.
#         Comparison set is taken from last 'short_pct'*100% of the dataset.
#         Score is normalized and able to be compared dataset independently.
#         Accuracy improves with samplesize."""
#         eps = np.finfo(float).eps
#
#         def fit_normal(arr: np.ndarray) -> tuple[float, float]:
#             mu = np.mean(arr)
#             sigma = np.std(arr)
#             return float(mu), float(sigma)
#
#         def normal_pdf(x, mu, sigma):
#             sigma = max(abs(float(sigma)), eps)
#             return (1 / (sigma * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x - mu) / sigma) ** 2)
#
#         short_size = max(int(X_full.shape[0] * short_pct), 1)   # length of comparison dataset
#         mu_full, sig_full = fit_normal(X_full)
#         mean_scale = mu_full if not np.isclose(mu_full, 0.0) else 1.0
#
#         # relative quadratic error
#         e_full = ((X_full - mu_full) / mean_scale) ** 2
#         e_short = e_full[-short_size:]
#
#         # z-transform full error set
#         mu_e_full, sig_e_full = fit_normal(e_full)
#         if np.isclose(sig_e_full, 0.0):
#             return 1.0
#
#         z_full = (e_full - mu_e_full) / sig_e_full
#
#         # z-transform short error set after full dataset parameters
#         z_short = (e_short - mu_e_full) / sig_e_full
#
#         # get distribution areas
#         mu_z_full, sig_z_full = fit_normal(z_full)
#         mu_z_short, sig_z_short = fit_normal(z_short)
#
#         # calculate distribution overlap
#         def overlap_between_normals(mu1, sigma1, mu2, sigma2, num_points=10000):
#             if np.isclose(sigma1, 0.0) and np.isclose(sigma2, 0.0):
#                 similarity = 1.0 if np.isclose(mu1, mu2) else 0.0
#                 return {
#                     "overlap_area": similarity,
#                     "area1": 1.0,
#                     "area2": 1.0,
#                     "similarity": similarity,
#                     "difference": 1 - similarity
#                 }
#
#             sigma1 = max(abs(float(sigma1)), eps)
#             sigma2 = max(abs(float(sigma2)), eps)
#
#             # Define a reasonable range covering both distributions
#             min_x = min(mu1 - 4 * sigma1, mu2 - 4 * sigma2)
#             max_x = max(mu1 + 4 * sigma1, mu2 + 4 * sigma2)
#
#             x = np.linspace(min_x, max_x, num_points)
#
#             pdf1 = normal_pdf(x, mu1, sigma1)
#             pdf2 = normal_pdf(x, mu2, sigma2)
#
#             # Overlapping area = integral of min(pdf1, pdf2)
#             overlap = np.trapezoid(np.minimum(pdf1, pdf2), x)
#
#             # Individual areas (should be ~1, but computed numerically)
#             area1 = np.trapezoid(pdf1, x)
#             area2 = np.trapezoid(pdf2, x)
#
#             # Similarity score (overlap coefficient)
#             difference = area1 + area2 - (2*overlap)
#             similarity = 1 - difference
#
#             return {
#                 "overlap_area": overlap,
#                 "area1": area1,
#                 "area2": area2,
#                 "similarity": similarity,
#                 "difference": difference
#             }
#
#         a = overlap_between_normals(mu_z_full, sig_z_full, mu_z_short, sig_z_short)
#         return a['similarity']
#
#
#     def draw_colorbar(self, heat: pd.DataFrame, fig, im, width: int, row_height: float, thresholds):
#         _, zero, low_err, high_err, _ = thresholds
#
#         fig_width = width + self.free_width
#         fig_height = heat.shape[0] * row_height + row_height
#
#         left = (self.free_width * (2 / 3)) / fig_width
#         right = 1 - (self.free_width * (1 / 3)) / fig_width
#         top = self._calculate_top_margin(fig_height)
#
#         cbar_bottom = top + self.c_bar_gap / fig_height
#         cbar_height = self.c_bar_height / fig_height
#         cbar_ax = fig.add_axes([left, cbar_bottom, right - left, cbar_height])
#
#         cbar = fig.colorbar(mappable=im, cax=cbar_ax, orientation='horizontal', label="Fehlerrate in %")
#         cbar.set_ticks([zero, low_err, high_err])
#         cbar.set_ticklabels([
#             f"{int(zero)}: no imports / start of blue",
#             f"{int(low_err)}: start of yellow",
#             f"{int(high_err)}: start of red",
#         ])
#
#     def _configurate_diagram_container(self, heat: pd.DataFrame, width: int, row_height: float):
#         fig_width = width + self.free_width
#         fig_height = heat.shape[0] * row_height + row_height
#         fig, ax = plt.subplots(figsize=(fig_width, fig_height), dpi=200)
#         return fig, np.ravel(ax)
#
#     def _calculate_top_margin(self, fig_height: float) -> float:
#         colorbar_section = self.c_bar_height + self.c_bar_gap
#         return 1 - colorbar_section / fig_height
#
#     def _adjust_layout(self, fig, width: int, heat: pd.DataFrame, row_height: float):
#         fig_width = width + self.free_width
#         fig_height = heat.shape[0] * row_height + row_height
#         plt.subplots_adjust(
#             top=self._calculate_top_margin(fig_height),
#             bottom=row_height / fig_height,
#             left=0.01,
#             right=(fig_width - self.free_width) / fig_width
#         )
#
#
# class ChartManager:
#     def __init__(self, mapper: ConfluenceNodeMapper, csv_paths: list = None, max_days: int = 42):
#         self.mapper = mapper
#         self.csv_paths = csv_paths if csv_paths is not None else []
#         self.max_days = max_days
#
#     def generate_heat(self, save_path: str):
#         """
#         This method manages the collection of needed error rate data and initializes the Heatmap generation factory.
#         """
#         hm = HeatMapFactory()
#         data = pd.DataFrame()
#
#         # collect all clinics
#         for path in self.csv_paths:
#             df = pd.read_csv(path, sep=";")
#             df = df.convert_dtypes()
#
#             clinic_id = self.__get_clinic_num(path)
#             clinic_name = self.mapper.get_node_value_from_mapping_dict(clinic_id, "COMMON_NAME")
#             df['clinic_id'] = np.repeat(clinic_id, df.shape[0])
#             df['clinic_name'] = np.repeat(clinic_name, df.shape[0])
#
#             data = pd.concat([data, df], ignore_index=True)
#
#         data = data[['date', 'clinic_id', 'clinic_name', 'daily_error_rate']]
#
#         # format column types
#         for col in data.columns:
#             # Try numeric
#             converted = pd.to_numeric(data[col], errors="coerce")
#             if converted.notna().sum() > 0:
#                 data[col] = converted
#                 continue
#             # Try datetime64
#             converted = pd.to_datetime(data[col], errors="coerce", utc=True)
#             if converted.notna().sum() > 0:
#                 data[col] = converted.dt.normalize()
#                 continue
#         hm.generate_diagram(df=data.fillna(-10), save_path=save_path)
#
#     def __get_clinic_num(self, path: str):
#         """
#         Returns a clinic number contained in a given path. Required syntax: .../{clinic num}_...
#         """
#         num = path.split('/')[-1].split("_")[0]
#         return num
#
#     def __read_error_rates(self, csv_file):
#         """
#         This method extracts error rates and date information from their respective columns in a csv file. Empty error
#         rates will be marked with a negative value
#         """
#         error_rates_df = []
#
#         _df = pd.read_csv(csv_file, sep=';')
#         try:
#             _df['date'] = pd.to_datetime(_df['date'], format='%Y-%m-%d %H:%M:%S.%f%z')
#         except Exception as e:
#             print(f'fixing error: {e}')
#             _df = pd.read_csv(csv_file, sep=',')
#             _df['date'] = pd.to_datetime(_df['date'], format='%Y-%m-%d %H:%M:%S.%f%z')
#         _df = _df.sort_values(by='date')
#         _date = [x.strftime('%d-%m') for x in _df['date']]
#
#         _df[_df == '-'] = -1.0
#         _df['daily_error_rate'] = _df['daily_error_rate'].apply(lambda x: float(x))
#         _error_rates = _df['daily_error_rate'].to_numpy()
#
#         return _date, _error_rates
