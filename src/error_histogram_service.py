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
    def generate_diagram(self, df: pd.DataFrame, save_path: str = None, timeframe=30, row_height=0.4, width=12):
        pivoted = df[['clinic_name', 'date', 'error_rate']] \
            .pivot(index='date', columns='clinic_name', values='error_rate').reset_index()

        # keep only dates inside time window
        max_date = pivoted.date.max()
        cutoff = max_date - pd.Timedelta(days=timeframe)
        window = pivoted.loc[pivoted.date >= cutoff].sort_values('date', ascending=True)    # filter columns inside time window
        heat = window.T
        heat.columns = heat.iloc[0]
        heat = heat.iloc[1:]


        # Define the heat-colors and thresholds (absolute values)
        colors = [
            'black',
            'mediumblue',
            'yellow',
            'yellow',
            'red'
        ]
        empty = -10
        zero = 0
        low_err = 1
        high_err = 5
        extr_err = 10
        bounds = np.array([empty, zero, low_err, high_err, extr_err, extr_err*2])-0.00001

        # set bounds for diagram containers
        dia_width = width
        dia_height = heat.shape[0] * row_height
        free_width = 4
        fig_width = dia_width + free_width
        fig_height = dia_height + row_height


        l_margin = (free_width*(2/3))/fig_width
        r_margin = 1-((free_width*(1/3))/fig_width)
        b_margin = row_height/fig_height


        # Create the heatmap with its configurations
        cmap = mc.ListedColormap(colors)
        norm = mc.BoundaryNorm(bounds, cmap.N)
        fig, ax = plt.subplots(figsize=(fig_width, fig_height))

        # plt.figure(figsize=(width, heat.shape[0] * row_height))   # width: 15 inch, height: 0.4 inch/row
        extent = (0, heat.shape[1], 0, heat.shape[0])

        yticks = np.arange(len(heat.index))

        ax.set_yticks(ticks=yticks+0.5, labels=heat.index, fontsize=10)    # labels: clinic_names

        mask = heat.columns.day % 5 == 0
        xticks = np.where(mask)[0]
        xlabels = heat.columns[mask].strftime("%d %b")
        ax.set_xticks(ticks=xticks, labels=xlabels, rotation=0, ha="center", fontsize=8)

        ax.hlines(yticks, xmin=0, xmax=heat.shape[1], color='grey', linewidth=0.5)

        im = ax.imshow(heat.to_numpy().tolist(), cmap=cmap, norm=norm, aspect="auto", extent=extent)
        cbar = fig.colorbar(mappable=im, ax=ax, label="Error Rate in %",)
        cbar.set_ticklabels(ticklabels=["No Imports", f'{zero}, Online', f'{low_err}, Low error rate', f'{high_err}, High error rate', f'{extr_err}, Extreme error rate', ''])
        # plt.subplots_adjust(left=0.2)
        plt.subplots_adjust(
            top=1,
            bottom=b_margin,
            left=l_margin,
            right=r_margin
        )

        plt.savefig(save_path)
        print()


    def _order(self, data: pd.DataFrame):
        last_week_modifier = 6  # Factor by which the values from last week are multiplied by
        sorted_data = dict(
            sorted(
                data.items(),
                key=lambda item: sum(item[1][:-7]) + sum(x * last_week_modifier for x in item[1][-7:]) if len(
                    item[1]) > 7 else sum(
                    item[1]),
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
