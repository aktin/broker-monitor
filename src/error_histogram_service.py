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
    def plot(self, df: pd.DataFrame, timeframe=30):
        heat_dates = pd.date_range(start=min(df['date']), end=max(df['date']), freq='d').date
        clinics = df.clinic_name.unique()

        # fill missing dates with nan
        heat = pd.DataFrame()
        heat['clinic_name'] = clinics
        for date in heat_dates:
            heat[str(date)] = np.repeat(np.nan, len(clinics))

        for i in df.index:
            row = df.loc[i]
            date = row.date
            err_rate = float(-1 if row.daily_error_rate=='-' else row.daily_error_rate)

            heat.loc[(heat.clinic_name==row.clinic_name), str(date)] = err_rate

        heat_dates = heat.columns[-timeframe:-1]
        heat = heat[heat.columns[0:1].tolist()+heat_dates.tolist()]

        # Define the colors and thresholds (absolute values)
        colors = [
            'black',
            'mediumblue',
            'yellow',
            'yellow',
            'red'
        ]
        no_imp = -10
        zero = 0
        low_err = 1
        high_err = 5
        extr_err = 10
        bounds = np.array([no_imp, zero, low_err, high_err, extr_err, extr_err*2])-0.00001

        # Create the heatmap with its configurations
        cmap = mc.ListedColormap(colors)
        norm = mc.BoundaryNorm(bounds, cmap.N)
        plt.figure(figsize=(heat.shape[1] / 3, heat.shape[0] / 4))
        extent = (0, heat.shape[1], 0, heat.shape[0])

        plt.imshow(heat.drop(columns=['clinic_name']).astype(float).to_numpy().tolist(), cmap=cmap, norm=norm, aspect="auto", extent=extent)
        cbar = plt.colorbar(label="Error Rate in %")
        cbar.set_ticklabels(ticklabels=["No Imports", f'{zero}, Online', f'{low_err}, Low error rate', f'{high_err}, High error rate', f'{extr_err}, Extreme error rate', ''])
        plt.subplots_adjust(left=0.2)

        # Create horizontal lines and clinic labels for y axis
        yticks = np.arange(len(heat))
        plt.hlines(yticks, xmin=0, xmax=len(heat_dates), color='grey', linewidth=0.5)
        label_ticks = yticks + 0.5
        plt.yticks(ticks=label_ticks, labels=clinics, fontsize=10)
        plt.xticks(ticks=np.arange(len(heat_dates)), labels=heat_dates, rotation=90, ha="left", fontsize=8)
        plt.savefig('heatmap.png')

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
    def __init__(self, mapper: ConfluenceNodeMapper, csv_paths: list = None,
                 save_path: str = "error_rates_histogram.png", max_days: int = 42):
        self.mapper = mapper
        self.csv_paths = csv_paths if csv_paths is not None else []
        self.save_path = save_path
        self.max_days = max_days

    def heat_map(self):
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

        # format dates
        data['date'] = pd.to_datetime(data['date'], format='%Y-%m-%d %H:%M:%S.%f%z').dt.date

        hm.plot(data)
        plt.savefig(self.save_path)

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
