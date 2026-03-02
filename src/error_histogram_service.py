"""
@AUTHOR=Wiliam Hoy (whoy@ukaachen.de)
@VERSION=1.33
"""

import pandas as pd
import matplotlib.colors as mc
import matplotlib.pyplot as plt
import numpy as np
from src.common import ConfluenceNodeMapper


class HeatMapFactory:
    """Generates a Heatmap using pandas DataFrame data. Prepares data, styling of diagram and saves it. """
    def __init__(self, c_bar_height = 0.15, c_bar_gap = 1, free_width = 2):
        self.c_bar_height = c_bar_height
        self.c_bar_gap = c_bar_gap
        self.free_width = free_width

    def generate_diagram(self, df: pd.DataFrame, save_path: str = None, timeframe=30, row_height=0.5, width=10):
        heat = self._prepare_heatmap_data(df, timeframe)
        fig, ax = self._configurate_diagram_container(heat, width, row_height)
        im = self._draw_heatmap(ax, heat, row_height, timeframe)
        self._draw_colorbar(fig, im, heat, width, row_height)
        self._adjust_layout(fig, width, heat, row_height)
        plt.savefig(save_path)

    def _prepare_heatmap_data(self, df: pd.DataFrame, timeframe: int) -> pd.DataFrame:
        pivoted = df[['clinic_name', 'date', 'error_rate']].pivot(
            index='date', columns='clinic_name', values='error_rate'
        ).reset_index()

        max_date = pivoted.date.max()
        cutoff = max_date - pd.Timedelta(days=timeframe)
        windowed = pivoted.loc[pivoted.date >= cutoff].sort_values('date', ascending=True)

        heat = windowed.T
        heat.columns = heat.iloc[0].infer_objects()
        return heat.iloc[1:]

    def _configurate_diagram_container(self, heat: pd.DataFrame, width: int, row_height: float):
        fig_width = width + self.free_width
        fig_height = heat.shape[0] * row_height + row_height
        return plt.subplots(figsize=(fig_width, fig_height))

    def _build_colormap(self):
        colors = ['black', 'mediumblue', 'yellow', 'yellow', 'red']
        thresholds = np.array([-10, 0, 1, 5, 10, 20]) - 0.00001
        cmap = mc.ListedColormap(colors)
        norm = mc.BoundaryNorm(thresholds, cmap.N)
        return cmap, norm, thresholds

    def _draw_heatmap(self, ax, heat: pd.DataFrame, row_height, timeframe):
        cmap, norm, _ = self._build_colormap()

        extent = (0, heat.shape[1], 0, heat.shape[0])
        im = ax.imshow(heat.to_numpy().tolist(), cmap=cmap, norm=norm, aspect="auto", extent=extent)

        ax.set_title(f"Fehlerraten der letzten {timeframe} Tage")
        yticks = np.arange(len(heat.index))
        ax.set_yticks(ticks=yticks + 0.5, labels=heat.index, fontsize=20*row_height)
        ax.hlines(yticks, xmin=0, xmax=heat.shape[1], color='white', linewidth=1)

        fifth_day_mask = heat.columns.day % 5 == 0
        ax.set_xticks(
            ticks=np.where(fifth_day_mask)[0],
            labels=heat.columns[fifth_day_mask].strftime("%d %b"),
            rotation=0, ha="center", fontsize=8
        )
        return im

    def _draw_colorbar(self, fig, im, heat: pd.DataFrame, width: int, row_height: float):
        _, _, thresholds = self._build_colormap()
        _, zero, low_err, high_err, extr_err, _ = thresholds + 0.00001

        fig_width = width + self.free_width
        fig_height = heat.shape[0] * row_height + row_height

        left = (self.free_width * (2 / 3)) / fig_width
        right = 1 - (self.free_width * (1 / 3)) / fig_width
        top = self._calculate_top_margin(fig_height)

        cbar_bottom = top + self.c_bar_gap / fig_height
        cbar_height = self.c_bar_height / fig_height
        cbar_ax = fig.add_axes([left, cbar_bottom, right - left, cbar_height])

        cbar = fig.colorbar(mappable=im, cax=cbar_ax, orientation='horizontal', label="Fehlerrate in %")
        cbar.set_ticklabels([
            "No Imports",
            f"{int(zero)}, Online",
            f"{int(low_err)}, Low error rate",
            f"{int(high_err)}, High error rate",
            f"{int(extr_err)}, Extreme error rate",
            ""
        ])

    def _calculate_top_margin(self, fig_height: float) -> float:
        colorbar_section = self.c_bar_height + self.c_bar_gap
        return 1 - colorbar_section / fig_height

    def _adjust_layout(self, fig, width: int, heat: pd.DataFrame, row_height: float):
        fig_width = width + self.free_width
        fig_height = heat.shape[0] * row_height + row_height

        plt.subplots_adjust(
            top=self._calculate_top_margin(fig_height),
            bottom=row_height / fig_height,
            left=self.free_width / fig_width,
            right=0.95
        )

    def _order(self, data: pd.DataFrame):
        last_week_modifier = 6
        sorted_data = dict(
            sorted(
                data.items(),
                key=lambda item: sum(item[1][:-7]) + sum(x * last_week_modifier for x in item[1][-7:]) if len(
                    item[1]) > 7 else sum(item[1]),
                reverse=True
            )
        )
        return sorted_data

class ChartManager:
    def __init__(self, mapper: ConfluenceNodeMapper, csv_paths: list = None, max_days: int = 42):
        self.mapper = mapper
        self.csv_paths = csv_paths if csv_paths is not None else []
        self.max_days = max_days

    def generate_heat(self, save_path: str):
        """
        This method manages the collection of needed error rate data and initializes the Heatmap generation factory.
        """
        hm = HeatMapFactory()
        data = pd.DataFrame()

        # collect all clinics
        for path in self.csv_paths:
            df = pd.read_csv(path, sep=";")
            df = df.convert_dtypes()

            clinic_id = self.__get_clinic_num(path)
            clinic_name = self.mapper.get_node_value_from_mapping_dict(clinic_id, "COMMON_NAME")
            df['clinic_id'] = np.repeat(clinic_id, df.shape[0])
            df['clinic_name'] = np.repeat(clinic_name, df.shape[0])

            data = pd.concat([data, df], ignore_index=True)

        # format column types
        for col in data.columns:
            # Try numeric
            converted = pd.to_numeric(data[col], errors="coerce")
            if converted.notna().sum() > 0:
                data[col] = converted
                continue
            # Try datetime64
            converted = pd.to_datetime(data[col], errors="coerce", utc=True)
            if converted.notna().sum() > 0:
                data[col] = converted.dt.normalize()
                continue
        hm.generate_diagram(df=data, save_path=save_path)

    def __get_clinic_num(self, path: str):
        """
        Returns a clinic number contained in a given path. Required syntax: .../{clinic num}_...
        """
        num = path.split('/')[-1].split("_")[0]
        return num

    def __read_error_rates(self, csv_file):
        """
        This method extracts error rates and date information from their respective columns in a csv file. Empty error
        rates will be marked with a negative value
        """
        error_rates_df = []

        _df = pd.read_csv(csv_file, sep=';')
        try:
            _df['date'] = pd.to_datetime(_df['date'], format='%Y-%m-%d %H:%M:%S.%f%z')
        except Exception as e:
            print(f'fixing error: {e}')
            _df = pd.read_csv(csv_file, sep=',')
            _df['date'] = pd.to_datetime(_df['date'], format='%Y-%m-%d %H:%M:%S.%f%z')
        _df = _df.sort_values(by='date')
        _date = [x.strftime('%d-%m') for x in _df['date']]

        _df[_df == '-'] = -1.0
        _df['daily_error_rate'] = _df['daily_error_rate'].apply(lambda x: float(x))
        _error_rates = _df['daily_error_rate'].to_numpy()

        return _date, _error_rates
