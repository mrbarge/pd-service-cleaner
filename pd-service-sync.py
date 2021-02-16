#!/bin/env python3
import subprocess
import logging
import argparse
import os
import sys

from pdpyras import APISession


def get_pd_services(session, team):
    services = list(session.iter_all('services', params={'query': 'devshift.org-hive-cluster', 'team_ids[]': [team], 'limit': 20}))
    return services


def get_ocm_clusters():
    try:
        pout = subprocess.check_output(
            ['ocm', 'list', 'clusters', '--managed', '--columns', 'api.url', '--padding', '100']).decode('utf-8')
        # pretty crude fixer-upper of API URL to get the base domain... >_>
        clusters = [c.strip().replace('https://api.', '').replace(':6443', '') for c in pout.splitlines() if
                    c.strip() != 'API URL' and c.strip() != 'NONE']
        return clusters

    except OSError as err:
        logging.info('OCM command failed with error: {}'.format(str(err)))
        sys.exit(1)
    except subprocess.CalledProcessError as err:
        logging.info('OCM command failed with error: {}'.format(str(err)))
        sys.exit(1)
    except ValueError as err:
        logging.info(
            'Output of command failed to parse with error: {}'.format(str(err)))
        sys.exit(1)


def is_staging(service, escalation_policy):
    """
    Determine if a service belongs to a staging cluster or not
    :param service:
    :return:
    """
    # Is the Escalation Policy Silent Test?
    if service['escalation_policy']['id'] != escalation_policy:
        return False
    # Is it a Hive-managed cluster?
    if 'A managed hive created cluster' not in service['description']:
        return False
    # Is it a basedomain that indicates staging?
    if not (str(service['name']).endswith('s1.devshift.org-hive-cluster') or str(service['name']).endswith(
            's2.devshift.org-hive-cluster')):
        return False
    return True


def is_active_service(service, clusters):
    """
    Return true if the supplied PD service matches a cluster in the supplied list of cluster basedomains
    :param service:
    :param clusters:
    :return:
    """
    for cluster in clusters:
        if cluster in service['name']:
            return True


def init_pd(api_token):
    """
    Initialise PD API session
    :param api_token:
    :return:
    """
    if os.path.isfile(api_token):
        with open(api_token, 'r') as file:
            api_token = file.read().replace('\n', '')
    return APISession(api_token)


def init_logging():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(name)s:%(message)s')


def init_argparse():
    """
    Initialises the command-line argument parser
    :return: parser instance
    """
    parser = argparse.ArgumentParser(description='PagerDuty Service Syncer')
    parser.add_argument('--pd_api_token', '-a', required=False, default=os.environ.get('PD_API_TOKEN'),
                        help='Path to file containing PD API Token [required]')
    parser.add_argument('--escalation_policy', '-e', required=False, default='PNCPMTV',
                        help='Escalation policy ID to identify clusters')
    parser.add_argument('--team', '-t', required=False,
                        help='Team owning clusters to delete')
    parser.add_argument('--dry-run', '-d', required=False, action='store_true',
                        help='Perform a dry run')

    return parser


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    init_logging()
    parser = init_argparse()
    args = parser.parse_args()

    logging.info("Retrieving current list of OCM staging clusters")
    clusters = get_ocm_clusters()
    pd_session = init_pd(args.pd_api_token)
    logging.info("Retrieving current list of PagerDuty services")
    services = get_pd_services(pd_session, args.team)

    for service in services:
        if not is_staging(service, args.escalation_policy):
            continue
        if is_active_service(service, clusters):
            continue

        # found a deletion candidate
        logging.info(f"Deleting service {service['name']} / {service['id']}")
        if not args.dry_run:
           pd_session.rdelete(f"/services/{service['id']}")
