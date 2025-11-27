# -*- coding: utf-8 -*
"""
Created on 26.06.2022
@AUTHOR=Alexander Kombeiz (akombeiz@ukaachen.de)
"""

#
#      Copyright (c) 2022  AKTIN
#
#      This program is free software: you can redistribute it and/or modify
#      it under the terms of the GNU Affero General Public License as
#      published by the Free Software Foundation, either version 3 of the
#      License, or (at your option) any later version.
#
#      This program is distributed in the hope that it will be useful,
#      but WITHOUT ANY WARRANTY; without even the implied warranty of
#      MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#      GNU Affero General Public License for more details.
#
#      You should have received a copy of the GNU Affero General Public License
#      along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
#

import os
import sys
from abc import ABC, abstractmethod
from email.mime.text import MIMEText

import bs4
import pandas as pd
from dateutil import parser
from packaging import version

from common import MailSender, TextWriter
from common import Main, ConfluenceConnection, ConfluenceNodeMapper, InfoCSVHandler, ResourceLoader, SingletonABCMeta, \
    SingletonMeta, TimestampHandler


# TODO: send mail on high error rate
class MailTemplateHandler(ResourceLoader, ABC):
    """
    Base class for handling mail templates.
    """
    _template_name: str = None
    _text_subtype: str = 'html'
    _parser: str = 'html.parser'
    _encoding: str = 'iso-8859-1'

    @abstractmethod
    def get_mail_template_filled_with_information_from_template_page(self, template_page: str) -> MIMEText:
        pass

    @staticmethod
    def _format_date_string_to_german_format(date: str) -> str:
        d = parser.parse(date)
        return d.strftime('%d.%m.%Y')


class OfflineMailTemplateHandler(MailTemplateHandler):
    """
    Get mailing template for node status "offline" and fills it with content
    """
    _template_name: str = 'template_mail_offline.html'

    def get_mail_template_filled_with_information_from_template_page(self, template_page: str) -> MIMEText:
        soup = bs4.BeautifulSoup(template_page, self._parser)
        clinic_name = soup.find(class_='clinic_name').text
        last_contact = soup.find(class_='last_contact').text
        formatted_last_contact = self._format_date_string_to_german_format(last_contact)
        content = self._get_resource_as_string(self._template_name, self._encoding)
        content = content.replace('${clinic_name}', clinic_name)
        content = content.replace('${last_contact}', formatted_last_contact)
        mail = MIMEText(content, self._text_subtype, self._encoding)
        mail['Subject'] = "Automatische Information: AKTIN DWH Offline"
        return mail


class NoImportsMailTemplateHandler(MailTemplateHandler):
    """
    Get mailing template for node status "no imports" and fills it with content
    """
    _template_name: str = 'template_mail_no_imports.html'

    def __init__(self, node_id: str):
        super().__init__()
        self.__handler = InfoCSVHandler()
        self.__csv_path = self.__get_csv_file_path(os.getenv('DIR.WORKING'), node_id)

    def __get_csv_file_path(self, working_dir: str, node_id: str) -> str:
        node_dir = os.path.join(working_dir, node_id)
        name_csv = self.__handler.generate_node_csv_name(node_id)
        path_csv = os.path.join(node_dir, name_csv)
        return path_csv

    def get_mail_template_filled_with_information_from_template_page(self, template_page: str) -> MIMEText:
        soup = bs4.BeautifulSoup(template_page, self._parser)
        clinic_name = soup.find(class_='clinic_name').text
        last_write = soup.find(class_='last_write').text
        last_write = self.__get_last_import_date_from_csv() if last_write == '-' else last_write
        formatted_last_write = self._format_date_string_to_german_format(last_write)
        content = self._get_resource_as_string(self._template_name, self._encoding)
        content = content.replace('${clinic_name}', clinic_name)
        content = content.replace('${last_write}', formatted_last_write)
        mail = MIMEText(content, self._text_subtype, self._encoding)
        mail['Subject'] = "Automatische Information: AKTIN DWH Keine Imports"
        return mail

    def __get_last_import_date_from_csv(self) -> str:
        df = self.__handler.read_csv_as_df(self.__csv_path)
        series = df['last_write']
        filtered_series = series[series != '-']
        if filtered_series.empty:
            return '???'
        return filtered_series.iloc[-1]


class OutdatedVersionMailTemplateHandler(MailTemplateHandler):
    """
    Get mailing template for node status "outdated version" and fills it with content
    """
    _template_name: str = 'template_mail_outdated_version.html'

    def __init__(self):
        super().__init__()
        self.__current_version_dwh = os.getenv('AKTIN.DWH_VERSION')
        self.__current_version_i2b2 = os.getenv('AKTIN.I2B2_VERSION')

    def get_mail_template_filled_with_information_from_template_page(self, template_page: str) -> MIMEText:
        soup = bs4.BeautifulSoup(template_page, self._parser)
        clinic_name = soup.find(class_='clinic_name').text
        version_dwh = soup.find(class_='dwh-j2ee').text
        content = self._get_resource_as_string(self._template_name, self._encoding)
        content = content.replace('${clinic_name}', clinic_name)
        content = content.replace('${version_dwh}', version_dwh)
        content = content.replace('${current_version_dwh}', self.__current_version_dwh)
        content = content.replace('${current_version_i2b2}', self.__current_version_i2b2)
        mail = MIMEText(content, self._text_subtype, self._encoding)
        mail['Subject'] = 'Automatische Information: AKTIN DWH Version veraltet'
        return mail


class NotificationHandler(metaclass=SingletonABCMeta):
    _parser: str = 'html.parser'
    _my_status: str
    _handler: MailTemplateHandler

    def __init__(self):
        self._confluence_recipients_extractor = ConfluencePageRecipientsExtractor()
        self.__sent_mails_logger = SentMailsLogger()
        filename_tracking = '_'.join(['tracking', self._my_status.replace(' ', '_')])
        self._sent_mails_counter = ConsecutiveSentEmailsCounter(filename_tracking)
        self._mail_sender = MailSender()

    @abstractmethod
    def did_my_status_occur(self, template_page: str) -> bool:
        pass

    @abstractmethod
    def sent_my_mail_to_node(self, node_id: str, template_page: str):
        pass

    def log_my_sent_mail_to_node(self, node_id: str):
        self.__sent_mails_logger.log_sent_mail_for_node(node_id, self._my_status)

    def clean_my_status_for_node(self, node_id: str):
        self._sent_mails_counter.delete_entry_tracking_for_node(node_id)

    def create_or_update_my_status_for_node(self, node_id: str):
        self._sent_mails_counter.create_or_update_node_entry(node_id)

    def is_waiting_threshold_reached_for_node(self, node_id) -> bool:
        return self._sent_mails_counter.is_waiting_threshold_reached_for_node(node_id)


class OfflineNotificationHandler(NotificationHandler):
    _my_status: str = 'OFFLINE'

    def __init__(self):
        super().__init__()
        self._handler = OfflineMailTemplateHandler()

    def did_my_status_occur(self, template_page: str) -> bool:
        soup = bs4.BeautifulSoup(template_page, self._parser)
        element_status = soup.find(class_='status')
        status = element_status.find('ac:parameter', attrs={'ac:name': 'title'})
        return status.text == self._my_status

    def sent_my_mail_to_node(self, node_id: str, template_page: str):
        mail = self._handler.get_mail_template_filled_with_information_from_template_page(template_page)
        recipients = self._confluence_recipients_extractor.extract_all_recipients_for_node_id(node_id)
        if recipients:
            self._mail_sender.send_mail(recipients, mail)


class NoImportsNotificationHandler(NotificationHandler):
    _my_status: str = 'NO IMPORTS'

    def did_my_status_occur(self, template_page: str) -> bool:
        soup = bs4.BeautifulSoup(template_page, self._parser)
        element_status = soup.find(class_='status')
        status = element_status.find('ac:parameter', attrs={'ac:name': 'title'})
        return status.text == self._my_status

    def sent_my_mail_to_node(self, node_id: str, template_page: str):
        self._handler = NoImportsMailTemplateHandler(node_id)
        mail = self._handler.get_mail_template_filled_with_information_from_template_page(template_page)
        recipients = self._confluence_recipients_extractor.extract_all_recipients_for_node_id(node_id)
        if recipients:
            self._mail_sender.send_mail(recipients, mail)


class OutdatedVersionNotificationHandler(NotificationHandler):
    _my_status: str = 'DWH OUTDATED'
    _handler = OutdatedVersionMailTemplateHandler

    def __init__(self):
        super().__init__()
        self._handler = OutdatedVersionMailTemplateHandler()
        self.__current_version_dwh = os.getenv('AKTIN.DWH_VERSION')

    def did_my_status_occur(self, template_page: str) -> bool:
        soup = bs4.BeautifulSoup(template_page, self._parser)
        dwh_version = soup.find(class_='dwh-j2ee').text
        formatted_version = dwh_version.replace('dwh-j2ee-', '')
        if formatted_version and formatted_version != '-':
            return version.parse(self.__current_version_dwh) > version.parse(formatted_version)
        return False

    def sent_my_mail_to_node(self, node_id: str, template_page: str):
        mail = self._handler.get_mail_template_filled_with_information_from_template_page(template_page)
        recipients = self._confluence_recipients_extractor.extract_all_recipients_for_node_id(node_id)
        if recipients:
            self._mail_sender.send_mail(recipients, mail)


class ConfluencePageRecipientsExtractor(metaclass=SingletonMeta):
    """
    Extracts correspondants for broker node from another confluence page
    """
    __confluence_email_list: str = 'E-Mail-Verteiler'

    def __init__(self):
        """
        Retrieves the recipients data from the Confluence email list page and prepares it for extraction.
        """
        confluence = ConfluenceConnection()
        confluence_email_page = confluence.get_page_content(self.__confluence_email_list)
        email_tables = pd.read_html(confluence_email_page)
        df = email_tables[0]
        df['Node ID'] = pd.to_numeric(df['Node ID'])
        df = df.fillna('')
        self.__email_df = df

    def extract_all_recipients_for_node_id(self, node_id: str) -> list:
        ed_recipients = self.__extract_ed_recipients_for_node_id(node_id)
        it_recipients = self.__extract_it_recipients_for_node_id(node_id)
        ed_recipients.extend(it_recipients)
        unique_recipients = list(dict.fromkeys(ed_recipients))
        return unique_recipients

    def __extract_ed_recipients_for_node_id(self, node_id: str) -> list:
        """
        Extracts ED (Emergency Department) recipients for the specified node ID.
        Only the main contacts (Hauptansprechpartner) are used (usually only one).
        Contacts can be blacklisted by setting a value in the appropriate column in Confluence.
        """
        contacts_list = []
        recipients_df = self.__get_recipients_df_for_node_id(node_id, 'Notaufnahme')
        main_contacts = recipients_df[(recipients_df['Hauptansprechpartner?'] != '') & (
                recipients_df['Abgemeldet von Monitor-Benachrichtigungen?'] == '')]
        contacts_series = main_contacts['Kontakt']
        for contact in contacts_series:
            contacts_list.append(contact)
        return contacts_list

    def __extract_it_recipients_for_node_id(self, node_id: str) -> list:
        """
        Extracts IT recipients for the specified node ID.
        All contacts are used.
        Contacts can be blacklisted by setting a value in the appropriate column in Confluence.
        """
        contacts_list = []
        recipients_df = self.__get_recipients_df_for_node_id(node_id, 'IT')
        main_contacts = recipients_df[recipients_df['Abgemeldet von Monitor-Benachrichtigungen?'] == '']
        contacts_series = main_contacts['Kontakt']
        for contact in contacts_series:
            contacts_list.append(contact)
        return contacts_list

    def __get_recipients_df_for_node_id(self, node_id: str, recipients_type: str) -> pd.DataFrame:
        """
        Retrieves the recipients dataframe for the specified node ID and recipient type.
        """
        idx_list = self.__email_df.index[self.__email_df['Node ID'] == int(node_id)].tolist()
        node_df = self.__email_df.iloc[idx_list]
        recipients_df = node_df[node_df['Ansprechpartner für'] == recipients_type]
        return recipients_df


class ConsecutiveSentEmailsCounter:
    """
    Checks when the last email was sent to node correspondants (to avoid notification spamming)
    """
    __tracking_dict: dict = {}
    __default_weeks_notification_interval = 1

    def __init__(self, filename: str):
        self.__filepath = os.path.join(os.getenv('DIR.WORKING'), f'{filename}.json')
        self.__timestamp = TimestampHandler()
        self.__mapper = ConfluenceNodeMapper()
        self.__writer = TextWriter()
        self.__writer.init_new_file_if_nonexisting(self.__filepath)
        self.__tracking_dict = self.__writer.load_txt_file_as_dict(self.__filepath)

    def create_or_update_node_entry(self, node_id: str):
        self.__tracking_dict[node_id] = self.__timestamp.get_current_date()
        self.__writer.save_dict_as_txt_file(self.__tracking_dict, self.__filepath)

    def delete_entry_tracking_for_node(self, node_id: str):
        if node_id in self.__tracking_dict:
            del self.__tracking_dict[node_id]
            self.__writer.save_dict_as_txt_file(self.__tracking_dict, self.__filepath)

    def is_waiting_threshold_reached_for_node(self, node_id: str) -> bool:
        """
        Checks if the waiting threshold is reached for the specified node ID.
        The waiting threshold is determined by the 'WEEKS_NOTIFICATION_INTERVAL' value in the node mapping.
        If the value is not set, the default threshold is 1 week.
        Returns True if the node is not in the tracking_dict as waiting threshold would be 0.
        """
        if node_id in self.__tracking_dict:
            threshold = self.__mapper.get_node_value_from_mapping_dict(node_id, 'WEEKS_NOTIFICATION_INTERVAL')
            if not threshold or threshold is None:
                threshold = self.__default_weeks_notification_interval
            last_sent = self.__tracking_dict.get(node_id)
            current_date = self.__timestamp.get_current_date()
            delta = self.__timestamp.get_timedelta_in_absolute_hours(last_sent, current_date)
            delta_in_weeks = delta / 168
            return delta_in_weeks > threshold
        return True


class SentMailsLogger(metaclass=SingletonMeta):
    """
    Logs all sent mail to corresponding nodes (for traceability)
    """

    def __init__(self):
        self.__working_dir = os.getenv('DIR.WORKING')
        self.__writer = TextWriter()
        self.__timestamp = TimestampHandler()

    def log_sent_mail_for_node(self, node_id: str, status: str):
        """
        Logs the sent mail for a specific node with the given status.
        """
        log_path = self.__generate_mails_log_path(node_id)
        current = self.__timestamp.get_current_date()
        data = f'{current} : Sent mail for status {status} to node id {node_id}\n'
        self.__writer.write_data_to_file(data, log_path)

    def __generate_mails_log_path(self, node_id: str) -> str:
        node_working_dir = os.path.join(self.__working_dir, node_id)
        filename = f'{node_id}_sent_mails.log'
        return os.path.join(node_working_dir, filename)


class NodeEventNotifierManager:
    """
    Manager class for notifying node recipients on emergency status events.
    """

    def __init__(self):
        self.__confluence = ConfluenceConnection()
        self.__mapper = ConfluenceNodeMapper()
        self.__offline = OfflineNotificationHandler()
        self.__no_imports = NoImportsNotificationHandler()
        self.__outdated_version = OutdatedVersionNotificationHandler()

    def notify_node_recipients_on_emergency_status(self):
        for node_id in self.__mapper.get_all_keys():
            pagename = self.__mapper.get_node_value_from_mapping_dict(node_id, 'COMMON_NAME')
            if self.__confluence.does_page_exists(pagename):
                page = self.__confluence.get_page_content(pagename)
                for notifier in (self.__offline, self.__no_imports, self.__outdated_version):
                    if notifier.did_my_status_occur(page):
                        if notifier.is_waiting_threshold_reached_for_node(node_id):
                            notifier.sent_my_mail_to_node(node_id, page)
                            notifier.log_my_sent_mail_to_node(node_id)
                            notifier.create_or_update_my_status_for_node(node_id)
                    else:
                        notifier.clean_my_status_for_node(node_id)


if __name__ == '__main__':
    if len(sys.argv) == 1:
        raise SystemExit(f'Usage: python {__file__} <path_to_config.toml>')
    Main.main(sys.argv[1], lambda: NodeEventNotifierManager().notify_node_recipients_on_emergency_status())
