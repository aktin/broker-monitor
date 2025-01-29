"""
@AUTHOR=William Hoy (whoy@ukaachen.de)
@VERSION=1.33
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import matplotlib.colors as mc
import matplotlib.pyplot as plt
import numpy as np
from django.utils.datetime_safe import datetime
from pandas.errors import EmptyDataError

from src.common import ConfluenceNodeMapper


class HeatMapFactory:
    def plot(self, data: dict, dates: list):
        sorted_data = self._order_dict(data)
        clinics = list(sorted_data.keys())
        data_matrix = np.array(list(sorted_data.values()))

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
        plt.figure(figsize=(data_matrix.shape[1] / 3, data_matrix.shape[0] / 4))
        extent = (0, data_matrix.shape[1], 0, data_matrix.shape[0])
        plt.imshow(data_matrix, cmap=cmap, norm=norm, aspect="auto", extent=extent)
        cbar = plt.colorbar(label="Error Rate in %")
        cbar.set_ticklabels(ticklabels=["No Imports", f'{zero}, Online', f'{low_err}, Low error rate', f'{high_err}, High error rate', f'{extr_err}, Extreme error rate', ''])
        plt.subplots_adjust(left=0.2)

        # Create horizontal lines and clinic labels for y axis
        ticks = np.arange(len(data_matrix))
        plt.hlines(ticks, xmin=0, xmax=data_matrix.shape[1], color='grey', linewidth=0.5)
        label_ticks = ticks + 0.5
        plt.yticks(ticks=label_ticks, labels=clinics[::-1], fontsize=10)
        plt.xticks(ticks=np.arange(len(dates)), labels=dates, rotation=90, ha="left", fontsize=8)
        plt.savefig('heatmap.png')

    def _order_dict(self, data: dict):
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
        data = {}
        dates = []

        def process_path(path):
            try:
                _dates, error_rates = self.__read_error_rates(path)
                error_rates = error_rates[-self.max_days:]
                _dates = _dates[-self.max_days:]

                clinic_id = self.__get_clinic_num(path)
                clinic_name = self.mapper.get_node_value_from_mapping_dict(clinic_id, "COMMON_NAME")

                #use data from last year or generate empty cells to keep diagram structure
                if len(error_rates) < self.max_days:
                    try:
                        last_year_path = path.replace(str(datetime.today().year), str(datetime.today().year-1))
                        _dates_ly, error_rates_ly = self.__read_error_rates(last_year_path)
                        remaining_days = self.max_days-len(error_rates)
                        error_rates_ly = error_rates_ly[-remaining_days:]
                        _dates_ly = _dates_ly[-remaining_days:]
                        error_rates = np.append(error_rates_ly, error_rates)
                        _dates = np.append(_dates_ly, _dates)
                    except Exception as e:
                        remaining_days = self.max_days - len(error_rates)
                        error_rates = np.append(np.array([[-1] * remaining_days]), error_rates)
                        _dates = np.append(np.array([["-"] * remaining_days]), np.array(_dates))

                data[clinic_name] = error_rates
                return _dates
            except Exception as e:
                print(f"Error processing {path}: {e}")
                return None

        with ThreadPoolExecutor() as executor:
            futures = {executor.submit(process_path, path): path for path in self.csv_paths}
            for future in as_completed(futures):
                result = future.result()
                if len(result)==self.max_days:
                    # data is a dictionary containing clinic names as keys and their error rates in an array as the
                    # value. Dates is an array containing the correspondant dates, the error rates refer to, and will be
                    # displayed on the x-axis of the diagram
                    dates = result
        if len(dates) == 0:
            raise EmptyDataError('dates could not be extracted from stats file')
        hm.plot(data, dates)
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
