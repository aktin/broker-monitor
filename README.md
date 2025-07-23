## broker-monitor 

A monitoring system for the [AKTIN Broker](https://github.com/aktin/broker) that tracks node activity, generates reports, and sends automated alerts. The system consists of several specialized scripts that work together to provide comprehensive monitoring. All reusable components are stored in `common.py`:

* `node_to_csv.py` - Primary data collector:
    - Retrieves node statistics (connections, imports, errors) from the broker
    - Tracks software versions and configurations
    - Stores all data in structured CSV and text files for analysis
    - Rotates files yearly to manage storage
  

* `csv_to_confluence.py` - Reporting system:
    - Processes collected node data into readable formats
    - Generates individual node status pages in Confluence
    - Creates summary dashboards with overall network health
    - Produces visualizations like error rate heatmaps
    - Updates pages incrementally to maintain history


* `email_service.py` - Automated alerting system:
    - Monitors nodes for critical states (offline, no imports, outdated)
    - Notifies relevant stakeholders via email when issues detected
    - Manages notification frequency to prevent alert fatigue
    - Maintains logs of all sent communications


* `file_backup_service.py` - Data preservation service:
    - Backs up all node-related files to Confluence
    - Preserves CSVs, logs, and configuration data
    - Ensures data availability for auditing and analysis


### Usage

A TOML configuration file with the following content is required to run the scripts (see also the example in `test\resources`):

| Scope      | Key               | Description                                                                                                                                | Example                                  |
|------------|-------------------|--------------------------------------------------------------------------------------------------------------------------------------------|------------------------------------------|
| BROKER     | URL               | URL to your broker server                                                                                                                  | http://localhost:8080                    |
| BROKER     | API_KEY           | API key of your broker server administrator                                                                                                | xxxAdmin1234                             |
| DIR        | WORKING           | Working directory of the script. Directories for each connected node to store the retrieved information are created here.                  | /opt                                     |
| DIR        | RESOURCES         | Path to the directory with HTML templates and other resources                                                                              | /opt/resources                           |
| CONFLUENCE | URL               | URL to your confluence server                                                                                                              | http://my-confluence.com                 |
| CONFLUENCE | SPACE             | Your Confluence space where the pages with node information should be created                                                              | MY_SPACE                                 |
| CONFLUENCE | TOKEN             | Your token for authentication in Confluence                                                                                                | jAzMjQ4Omy                               |
| CONFLUENCE | MAPPING_JSON      | Path to the confluence json mapping file                                                                                                   | /opt/mapping.json                        |
| SMTP       | SERVER            | URL to your mailing server                                                                                                                 | http://localhost:8888                    |
| SMTP       | USERNAME          | Your user of your mailing server                                                                                                           | myuser@myserver.net                      |
| SMTP       | PASSWORD          | The password to your mailing server user                                                                                                   | Hc5sGhdr2577                             |
| SMTP       | STATIC_RECIPIENTS | Static email recipients set as CC for each sent mail. Usually the support team is set here to keep track of sent mails and current events. | ["person1@mail.com", "person2@mail.com"] |
| AKTIN      | DWH_VERSION       | The current package version of aktin-notaufnahme-dwh.deb                                                                                   | 1.5.1rc1                                 |
| AKTIN      | I2B2_VERSION      | The current package version of aktin-notaufnahme-i2b2.deb                                                                                  | 1.5.3                                    |

The configuration file must be passed to the scripts as an input argument. Additionally, the script `common.py` must be located in the same folder as the executed script:

```
python3 node_to_csv.py <PATH_TO_CONFIG_TOML>
```

The script `csv_to_confluence.py` needs a mapping table (parameter `MAPPING_JSON` inside the config file) to map the ID of the broker nodes to static node-reladed information. An exemplary entry inside the
mapping looks like the following:

```
"99": {
    "COMMON_NAME": "[99] Default Clinic",
    "LONG_NAME": "Institute of Ninety-Nine",
    "JIRA_LABELS": [
      "label1",
      "label2",
    ],
    "HOSPITAL_INFORMATION_SYSTEM" : "HyperHIS",
    "IMPORT_INTERFACE": "SuperImporter V3.3",
    "THRESHOLD_HOURS_FAILURE" : 48,
    "WEEKS_NOTIFICATION_INTERVAL" : 2,
    "ROOT": {
        "PATIENT": "1.2.2",
        "ENCOUNTER": "1.2.45",
        "BILLING": "1.2.47"
    },
    "FORMAT": {
        "PATIENT": "1111",
        "ENCOUNTER": "2222",
        "BILLING": "3333"
    }
}
```

| Parameter                   | Description                                                                                                                                                                                                       | Example                                                                  |
|-----------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------|
| NODE_ID                     | Id of the corresponding node. Used to map the import statistics with other clinic-related information                                                                                                             | 99                                                                       |
| COMMON_NAME                 | Short qualified name of the node. Is used as the name of the created Confluence page. This is the only required key in the dictionary.                                                                            | [99] Default Clinic                                                      |
| LONG_NAME                   | Official name of the node/the institution. If this key is empty, the value "changeme" is used.                                                                                                                    | Institute of Ninety-Nine                                                 |
| JIRA_LABELS                 | List of labels to define a JIRA query and pass to a table for JIRA tickets inside the Confluence page. If this key is empty, an empty JIRA table is created in the Confluence page.                               | ["label1", "label2"]                                                     |
| THRESHOLD_HOURS_FAILURE     | Integer, after how many hours of no imports/no broker contact the status of the node is changed. If this key is empty, a default value of 24 is used.                                                             | 48                                                                       |
| WEEKS_NOTIFICATION_INTERVAL | Integer, after how many weeks after last notification the node should be notified again, if its state did not change. If this key is empty, a default value of 1 is used.                                         | 1                                                                        |
| CONSECUTIVE_IMPORT_DAYS     | Number of days that a continuous import should have taken place for the node to be considered "active". If this key is empty, a default value of 3 is used.                                                       | 5                                                                        |
| HOSPITAL_INFORMATION_SYSTEM | The hospital information system used by the node. If this key is empty, the value "changeme" is used.                                                                                                             | HyperHIS                                                                 |
| IMPORT_INTERFACE            | The AKTIN import interface used by the node. If this key is empty, the value "changeme" is used.                                                                                                                  | SuperImporter V3.3                                                       |
| ROOT                        | The root ids used in the CDAs of the node. "PATIENT", "ENCOUNTER" and "BILLING" are the only possible keys. Other keys are ignored. If a key is missing, the value "changeme" is used instead.                    | {"PATIENT": "1.2.2",<br/>"ENCOUNTER": "1.2.45",<br/>"BILLING": "1.2.47"} |
| FORMAT                      | The format of the extension ids used in the CDAs of the node. "PATIENT", "ENCOUNTER" and "BILLING" are the only possible keys. Other keys are ignored. If a key is missing, the value "changeme" is used instead. | {PATIENT": "1111",<br/>"ENCOUNTER": "2222",<br/>"BILLING": "3333"}       |

### Testing

To test the script, **integration-test.bat** and **integration-test.sh** are attached. To run an integration test, a running instance of [Docker](https://www.docker.com/) is required. The script will create a container to
simulate the [AKTIN Broker Server](https://github.com/aktin/broker/tree/master/broker-server) and a second container to run the scripts on. Every class of the scripts, which does not need a connection to Confluence or the
E-Mail-Server, is tested within the integration tests.

IMPORTANT: During the unit tests, the scripts create a temporary working folder and then delete it after the tests finished. Do not set `DIR.WORKING` in `test/resources/settings.toml` to an existing folder, as IT WILL BE DELETED automatically after the test.
