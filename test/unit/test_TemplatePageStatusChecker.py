import os
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from shutil import rmtree

import bs4
import pandas as pd
from pytz import timezone

this_path = Path(os.path.realpath(__file__))
path_src = os.path.join(this_path.parents[2], 'src')
sys.path.insert(0, path_src)

from common import InfoCSVHandler, ConfigReader
from csv_to_confluence import TemplatePageCSVInfoWriter, TemplatePageLoader, TemplatePageStatusChecker


class TestTemplatePageStatusChecker(unittest.TestCase):
    __DEFAULT_NODE_ID: str = '10'
    __DIR_WORKING: str = None
    __TEMPLATE: str = None

    @classmethod
    def setUpClass(cls):
        path_settings = os.path.join(this_path.parents[1], 'resources', 'settings.toml')
        ConfigReader().load_config_as_env_vars(path_settings)
        cls.__DIR_WORKING = os.environ['DIR.WORKING'] if os.environ['DIR.WORKING'] else os.getcwd()
        cls.__CHECKER = TemplatePageStatusChecker()
        cls.__CURRENT_YMD_HMS = datetime.now(timezone('Europe/Berlin')).strftime('%Y-%m-%d %H:%M:%S')
        cls.__CSV_HANDLER = InfoCSVHandler()
        cls.__CSV_INFO_WRITER = TemplatePageCSVInfoWriter()
        name_csv = InfoCSVHandler().generate_node_csv_name(cls.__DEFAULT_NODE_ID)
        cls.__DEFAULT_CSV_PATH = os.path.join(cls.__DIR_WORKING, cls.__DEFAULT_NODE_ID, name_csv)

    def setUp(self):
        self.__init_testing_template()
        self.__init_working_dir_with_empty_csv(self.__DEFAULT_NODE_ID)

    def tearDown(self):
        rmtree(self.__DIR_WORKING)

    def __init_testing_template(self):
        loader = TemplatePageLoader()
        page = loader.get_template_page()
        html = bs4.BeautifulSoup(page, 'html.parser')
        html.find(class_='last_contact').string.replace_with(self.__CURRENT_YMD_HMS)
        html.find(class_='last_write').string.replace_with(self.__CURRENT_YMD_HMS)
        html.find(class_='daily_imported').string.replace_with('1000')
        html.find(class_='daily_error_rate').string.replace_with('0.0')
        self.__TEMPLATE = str(html)

    def __init_working_dir_with_empty_csv(self, id_node: str):
        dir_working = os.path.join(self.__DIR_WORKING, id_node)
        if not os.path.exists(dir_working):
            os.makedirs(dir_working)
        df = pd.DataFrame(columns=self.__CSV_HANDLER.get_csv_columns())
        name_csv = self.__CSV_HANDLER.generate_node_csv_name(id_node)
        path_csv = os.path.join(self.__DIR_WORKING, id_node, name_csv)
        self.__CSV_HANDLER.write_data_to_file(df, path_csv)

    def test_default_values_for_online(self):
        page = self.__CHECKER.add_content_to_template_page(self.__TEMPLATE, self.__DEFAULT_NODE_ID)
        self.__check_title_and_color_of_status_element_on_page(page, 'ONLINE', 'Green')

    def test_last_contact_less_than_one_day_ago(self):
        date_yesterday = self.__get_current_date_moved_back_by_days_and_hours(0, 23)
        self.__set_value_in_template('last_contact', date_yesterday)
        page = self.__CHECKER.add_content_to_template_page(self.__TEMPLATE, self.__DEFAULT_NODE_ID)
        self.__check_title_and_color_of_status_element_on_page(page, 'ONLINE', 'Green')

    def test_last_contact_less_than_one_day_ago_updated_threshold(self):
        id_node = '3'
        self.__init_testing_template()
        self.__init_working_dir_with_empty_csv(id_node)
        date_yesterday = self.__get_current_date_moved_back_by_days_and_hours(0, 23)
        self.__set_value_in_template('last_contact', date_yesterday)
        page = self.__CHECKER.add_content_to_template_page(self.__TEMPLATE, id_node)
        self.__check_title_and_color_of_status_element_on_page(page, 'OFFLINE', 'Red')

    def test_last_contact_more_than_one_day_ago(self):
        date_past = self.__get_current_date_moved_back_by_days_and_hours(1, 1)
        self.__set_value_in_template('last_contact', date_past)
        page = self.__CHECKER.add_content_to_template_page(self.__TEMPLATE, self.__DEFAULT_NODE_ID)
        self.__check_title_and_color_of_status_element_on_page(page, 'OFFLINE', 'Red')

    def test_last_contact_more_than_one_day_ago_updated_threshold(self):
        id_node = '2'
        self.__init_testing_template()
        self.__init_working_dir_with_empty_csv(id_node)
        date_past = self.__get_current_date_moved_back_by_days_and_hours(1, 1)
        self.__set_value_in_template('last_contact', date_past)
        page = self.__CHECKER.add_content_to_template_page(self.__TEMPLATE, id_node)
        self.__check_title_and_color_of_status_element_on_page(page, 'ONLINE', 'Green')

    def test_last_write_less_than_one_day_ago(self):
        date_yesterday = self.__get_current_date_moved_back_by_days_and_hours(0, 23)
        self.__set_value_in_template('last_write', date_yesterday)
        page = self.__CHECKER.add_content_to_template_page(self.__TEMPLATE, self.__DEFAULT_NODE_ID)
        self.__check_title_and_color_of_status_element_on_page(page, 'ONLINE', 'Green')

    def test_last_write_less_than_one_day_ago_updated_threshold(self):
        id_node = '3'
        self.__init_testing_template()
        self.__init_working_dir_with_empty_csv(id_node)
        date_yesterday = self.__get_current_date_moved_back_by_days_and_hours(0, 23)
        self.__set_value_in_template('last_write', date_yesterday)
        page = self.__CHECKER.add_content_to_template_page(self.__TEMPLATE, id_node)
        self.__check_title_and_color_of_status_element_on_page(page, 'NO IMPORTS', 'Red')

    def test_last_write_more_than_one_day_ago(self):
        date_past = self.__get_current_date_moved_back_by_days_and_hours(1, 1)
        self.__set_value_in_template('last_write', date_past)
        page = self.__CHECKER.add_content_to_template_page(self.__TEMPLATE, self.__DEFAULT_NODE_ID)
        self.__check_title_and_color_of_status_element_on_page(page, 'NO IMPORTS', 'Red')

    def test_last_write_more_than_one_day_ago_updated_threshold(self):
        id_node = '2'
        self.__init_testing_template()
        self.__init_working_dir_with_empty_csv(id_node)
        date_past = self.__get_current_date_moved_back_by_days_and_hours(1, 1)
        self.__set_value_in_template('last_write', date_past)
        page = self.__CHECKER.add_content_to_template_page(self.__TEMPLATE, id_node)
        self.__check_title_and_color_of_status_element_on_page(page, 'ONLINE', 'Green')

    def test_empty_last_write(self):
        self.__set_value_in_template('last_write', '-')
        page = self.__CHECKER.add_content_to_template_page(self.__TEMPLATE, self.__DEFAULT_NODE_ID)
        self.__check_title_and_color_of_status_element_on_page(page, 'NO IMPORTS', 'Red')

    def test_no_daily_imports(self):
        self.__set_value_in_template('daily_imported', '-')
        self.__set_value_in_template('daily_updated', '-')
        page = self.__CHECKER.add_content_to_template_page(self.__TEMPLATE, self.__DEFAULT_NODE_ID)
        self.__check_title_and_color_of_status_element_on_page(page, 'ONLINE', 'Green')

    def test_error_rate_below_lower_threshold(self):
        self.__set_value_in_template('daily_error_rate', '0.99')
        page = self.__CHECKER.add_content_to_template_page(self.__TEMPLATE, self.__DEFAULT_NODE_ID)
        self.__check_title_and_color_of_status_element_on_page(page, 'ONLINE', 'Green')

    def test_error_rate_on_lower_threshold(self):
        self.__set_value_in_template('daily_error_rate', '1.0')
        page = self.__CHECKER.add_content_to_template_page(self.__TEMPLATE, self.__DEFAULT_NODE_ID)
        self.__check_title_and_color_of_status_element_on_page(page, 'LOW ERROR RATE', 'Yellow')

    def test_error_rate_above_lower_threshold(self):
        self.__set_value_in_template('daily_error_rate', '1.01')
        page = self.__CHECKER.add_content_to_template_page(self.__TEMPLATE, self.__DEFAULT_NODE_ID)
        self.__check_title_and_color_of_status_element_on_page(page, 'LOW ERROR RATE', 'Yellow')

    def test_error_rate_below_higher_threshold(self):
        self.__set_value_in_template('daily_error_rate', '4.99')
        page = self.__CHECKER.add_content_to_template_page(self.__TEMPLATE, self.__DEFAULT_NODE_ID)
        self.__check_title_and_color_of_status_element_on_page(page, 'LOW ERROR RATE', 'Yellow')

    def test_error_rate_on_higher_threshold(self):
        self.__set_value_in_template('daily_error_rate', '5.0')
        page = self.__CHECKER.add_content_to_template_page(self.__TEMPLATE, self.__DEFAULT_NODE_ID)
        self.__check_title_and_color_of_status_element_on_page(page, 'HIGH ERROR RATE', 'Yellow')

    def test_error_rate_above_higher_threshold(self):
        self.__set_value_in_template('daily_error_rate', '5.01')
        page = self.__CHECKER.add_content_to_template_page(self.__TEMPLATE, self.__DEFAULT_NODE_ID)
        self.__check_title_and_color_of_status_element_on_page(page, 'HIGH ERROR RATE', 'Yellow')

    def test_extreme_error_rate(self):
        self.__set_value_in_template('daily_error_rate', '10.01')
        page = self.__CHECKER.add_content_to_template_page(self.__TEMPLATE, self.__DEFAULT_NODE_ID)
        self.__check_title_and_color_of_status_element_on_page(page, 'EXTREME ERROR RATE', 'Red')

    def test_no_error_rate(self):
        self.__set_value_in_template('daily_error_rate', '-')
        page = self.__CHECKER.add_content_to_template_page(self.__TEMPLATE, self.__DEFAULT_NODE_ID)
        self.__check_title_and_color_of_status_element_on_page(page, 'ONLINE', 'Green')

    def test_no_consecutive_imports(self):
        df = pd.DataFrame(columns=self.__CSV_HANDLER.get_csv_columns())
        df['date'] = self.__create_list_of_current_weeks_dates()
        df['daily_imported'] = ['0', '1', '1', '0', '1', '0', '0']
        self.__CSV_HANDLER.write_data_to_file(df, self.__DEFAULT_CSV_PATH)
        page = self.__CHECKER.add_content_to_template_page(self.__TEMPLATE, self.__DEFAULT_NODE_ID)
        self.__check_title_and_color_of_status_element_on_page(page, 'TESTING', 'Blue')

    def test_consecutive_imports(self):
        df = pd.DataFrame(columns=self.__CSV_HANDLER.get_csv_columns())
        df['date'] = self.__create_list_of_current_weeks_dates()
        df['daily_imported'] = ['0', '0', '1', '1', '1', '0', '0']
        self.__CSV_HANDLER.write_data_to_file(df, self.__DEFAULT_CSV_PATH)
        page = self.__CHECKER.add_content_to_template_page(self.__TEMPLATE, self.__DEFAULT_NODE_ID)
        self.__check_title_and_color_of_status_element_on_page(page, 'ONLINE', 'Green')

    def test_custom_value_set_for_consecutive_imports(self):
        id_node = '3'
        self.__init_testing_template()
        self.__init_working_dir_with_empty_csv(id_node)
        df = pd.DataFrame(columns=self.__CSV_HANDLER.get_csv_columns())
        df['date'] = self.__create_list_of_current_weeks_dates()
        df['daily_imported'] = ['0', '1', '1', '1', '1', '1', '0']
        name_csv = self.__CSV_HANDLER.generate_node_csv_name(id_node)
        path_csv = os.path.join(self.__DIR_WORKING, id_node, name_csv)
        self.__CSV_HANDLER.write_data_to_file(df, path_csv)
        page = self.__CHECKER.add_content_to_template_page(self.__TEMPLATE, id_node)
        self.__check_title_and_color_of_status_element_on_page(page, 'TESTING', 'Blue')

    def test_consecutive_imports_higher_than_csv_rows(self):
        id_node = '2'
        self.__init_testing_template()
        self.__init_working_dir_with_empty_csv(id_node)
        df = pd.DataFrame(columns=self.__CSV_HANDLER.get_csv_columns())
        df['date'] = self.__create_list_of_current_weeks_dates()
        df['daily_imported'] = ['0', '1', '1', '1', '1', '1', '0']
        name_csv = self.__CSV_HANDLER.generate_node_csv_name(id_node)
        path_csv = os.path.join(self.__DIR_WORKING, id_node, name_csv)
        self.__CSV_HANDLER.write_data_to_file(df, path_csv)
        page = self.__CHECKER.add_content_to_template_page(self.__TEMPLATE, id_node)
        self.__check_title_and_color_of_status_element_on_page(page, 'ONLINE', 'Green')

    def test_no_gap_in_monitoring(self):
        df = pd.DataFrame(columns=self.__CSV_HANDLER.get_csv_columns())
        df['date'] = self.__create_list_of_current_weeks_dates()
        df['daily_imported'] = ['1', '1', '1', '1', '1', '1', '1']
        self.__CSV_HANDLER.write_data_to_file(df, self.__DEFAULT_CSV_PATH)
        page = self.__CHECKER.add_content_to_template_page(self.__TEMPLATE, self.__DEFAULT_NODE_ID)
        self.__check_title_and_color_of_status_element_on_page(page, 'ONLINE', 'Green')

    def test_gap_in_monitoring_today(self):
        df = pd.DataFrame(columns=self.__CSV_HANDLER.get_csv_columns())
        df['date'] = self.__create_list_of_current_weeks_dates()
        df.at[6, 'date'] = self.__get_current_date_moved_back_by_days_and_hours(days=1, hours=1)
        df['daily_imported'] = ['1', '1', '1', '1', '1', '1', '1']
        self.__CSV_HANDLER.write_data_to_file(df, self.__DEFAULT_CSV_PATH)
        page = self.__CHECKER.add_content_to_template_page(self.__TEMPLATE, self.__DEFAULT_NODE_ID)
        self.__check_title_and_color_of_status_element_on_page(page, 'GAP IN MONITORING', 'Red')

    def test_gap_in_monitoring_yesterday(self):
        df = pd.DataFrame(columns=self.__CSV_HANDLER.get_csv_columns())
        df['date'] = self.__create_list_of_current_weeks_dates()
        df.at[5, 'date'] = self.__get_current_date_moved_back_by_days_and_hours(days=1, hours=1)
        df['daily_imported'] = ['1', '1', '1', '1', '1', '1', '1']
        self.__CSV_HANDLER.write_data_to_file(df, self.__DEFAULT_CSV_PATH)
        page = self.__CHECKER.add_content_to_template_page(self.__TEMPLATE, self.__DEFAULT_NODE_ID)
        self.__check_title_and_color_of_status_element_on_page(page, 'GAP IN MONITORING', 'Red')

    def test_gap_in_monitoring_in_between(self):
        df = pd.DataFrame(columns=self.__CSV_HANDLER.get_csv_columns())
        df['date'] = self.__create_list_of_current_weeks_dates()
        df.at[3, 'date'] = self.__get_current_date_moved_back_by_days_and_hours(days=5, hours=0)
        df['daily_imported'] = ['1', '1', '1', '1', '1', '1', '1']
        self.__CSV_HANDLER.write_data_to_file(df, self.__DEFAULT_CSV_PATH)
        page = self.__CHECKER.add_content_to_template_page(self.__TEMPLATE, self.__DEFAULT_NODE_ID)
        self.__check_title_and_color_of_status_element_on_page(page, 'ONLINE', 'Green')

    def __create_list_of_current_weeks_dates(self) -> list:
        list_dates = []
        for x in range(6, -1, -1):
            date = self.__get_current_date_moved_back_by_days_and_hours(days=x, hours=0)
            list_dates.append(date)
        return list_dates

    def __set_value_in_template(self, key: str, value: str):
        html = bs4.BeautifulSoup(self.__TEMPLATE, 'html.parser')
        html.find(class_=key).string.replace_with(value)
        self.__TEMPLATE = str(html)

    @staticmethod
    def __get_current_date_moved_back_by_days_and_hours(days: int, hours: int) -> str:
        ts_current = datetime.now(timezone('Europe/Berlin'))
        ts_past = ts_current - timedelta(days=days, hours=hours)
        return ts_past.strftime('%Y-%m-%d %H:%M:%S')

    def __check_title_and_color_of_status_element_on_page(self, page: str, expected_title: str, expected_color: str):
        html = bs4.BeautifulSoup(page, 'html.parser')
        status = html.find(class_='status')
        param_title = status.findAll('ac:parameter', {'ac:name': 'title'})
        actual_title = param_title[0].string
        self.assertEqual(expected_title, actual_title)
        param_color = status.findAll('ac:parameter', {'ac:name': 'color'})
        actual_color = param_color[0].string
        self.assertEqual(expected_color, actual_color)


if __name__ == '__main__':
    unittest.main()
