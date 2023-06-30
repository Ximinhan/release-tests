#!/usr/bin/env python3
#coding:utf-8
import requests
import time
import json
from semver import VersionInfo
import yaml
import base64
import os
import sys
import re
import csv
import click

class Jobs(object):
    def __init__(self):
        self.url = 'https://amd64.ocp.releases.ci.openshift.org/api/v1/releasestream/4-stable/tags'
        # config the based URL here
        self.jobURL='https://api.github.com/repos/openshift/release/contents/ci-operator/config/openshift/openshift-tests-private/{}?ref=master'
        self.gangwayURL = "https://gangway-ci.apps.ci.l2s4.p1.openshiftapps.com/v1/executions/"
        self.prowJobURL = "https://prow.ci.openshift.org/prowjob?prowjob={}"

    # get_prow_headers func adds the Prow Token
    def get_prow_headers(self):
        token = os.getenv('APITOKEN')
        if token:
            headers = {'Authorization': 'Bearer ' + token.strip()}
            return headers
        else:
            print('No Prow API token found, exit...')
            sys.exit(0)

    def get_job_data(self, payload, upgrade_from, upgrade_to):
        data = {'job_execution_type': '1'}
        if payload is not None and upgrade_from is not None and upgrade_to is not None:
            print("Error! You cannot run e2e and upgrade test at the same time!")
            return None
        if payload is not None:
            data = {"job_execution_type": "1", 
                    "pod_spec_options": 
                    {"envs":  
                     {"RELEASE_IMAGE_LATEST": payload} 
                     } 
                }
        if upgrade_from is not None and upgrade_to is not None:
            data = {"job_execution_type": "1", 
                    "pod_spec_options": 
                    {"envs":  
                     {"RELEASE_IMAGE_LATEST": upgrade_from,
                       "RELEASE_IMAGE_TARGET": upgrade_to
                       }
                     } 
                }
        if upgrade_from is None and upgrade_to is not None:
            data = {"job_execution_type": "1", 
                    "pod_spec_options": 
                    {"envs":  
                     {
                       "RELEASE_IMAGE_TARGET": upgrade_to
                       }
                     } 
                }
        if upgrade_from is not None and upgrade_to is None:
            data = {"job_execution_type": "1", 
                    "pod_spec_options": 
                    {"envs":  
                     {"RELEASE_IMAGE_LATEST": upgrade_from
                       }
                     } 
                }
        return data
    
    def get_sha(self, url):
        res = requests.get(url=url, headers=self.get_github_headers())
        if res.status_code == 200:
            sha = json.loads(res.text)["sha"]
            print("sha: %s" % sha)
            return sha
        else:
            print(res.status_code, res.reason)
            return None
        
    def push_action(self, url, data):
        res = requests.put(url=url, json=data, headers=self.get_github_headers())
        if res.status_code == 200:
            print(res.reason)
        else:
            print(res.status_code, res.reason)

    def push_versions(self, content, file, run):
        url = "https://api.github.com/repos/openshift/release-tests/contents/_releases/{}?ref=record".format(file)
        base64Content = base64.b64encode(bytes(content, encoding='utf-8')).decode('utf-8')
        # print(base64Content)
        # check if the file exist
        res = requests.get(url=url, headers=self.get_github_headers())
        if res.status_code == 200:
            oldVersion = self.get_recored_version(url)
            if VersionInfo.parse(oldVersion) < VersionInfo.parse(content): 
                sha = self.get_sha(url)
                # sha is Required if you are updating a file.
                data = {"sha": sha,"content": base64Content,"branch": "record", "message":"got the latest version %s" % content,"committer":{"name":"Release Bot","email":"jianzhanbjz@github.com"}}
                self.push_action(url, data)
                if run:
                    default_file= "_releases/required-jobs.json"
                    channel = content[:-2]
                    self.run_required_jobs(channel, default_file)
            else:
                print("No update! since the recored version %s >= the new version %s" % (oldVersion, content))
        elif res.status_code == 404:
            print("file %s doesn't exist, create it." % url)
            data = {"content":base64Content,"branch": "record", "message":"got the latest version %s" % content,"committer":{"name":"Release Bot","email":"jianzhanbjz@github.com"}}
            self.push_action(url, data)
            if run:
                default_file= "_releases/required-jobs.json"
                channel = content[:-2]
                self.run_required_jobs(channel, default_file)
        else:
            print("Push error: %s, %s" % (res.status_code, res.reason))
    
    def save_results(self, content, file):
        file_json = file
        url = "https://api.github.com/repos/openshift/release-tests/contents/_releases/" + file
        base64Content = base64.b64encode(bytes(content, encoding='utf-8')).decode('utf-8')
        # print(base64Content)
        # check if the file exist
        res = requests.get(url=url, headers=self.get_github_headers())       

    def get_recored_version(self,url):
        try:
            # it will use the default master branch
            res = requests.get(url=url, headers=self.get_github_headers())
            if res.status_code == 200:
                return base64.b64decode(json.loads(res.text)["content"]).decode('utf-8').replace("\n", "")
            else:
                print("Fail to get recored version! %s:%s" % (res.status_code, res.reason))
                return None
        except Exception as e:
            print(e)

    def get_payloads(self, versions, push, run):
        if versions is None:
            print("Please input the correct version info...")
            sys.exit(0)
        version_list = versions.split(",")
        res = requests.get(url=self.url, timeout=5)
        if res.status_code != 200:
            print("Fail to get payload info, %s:%s" % (res.status_code, res.reason))
            sys.exit(1)
        dict = json.loads(res.text)
        # Current three z-stream releases
        # releaseVersions = ["4.10.0", "4.11.0", "4.12.0"]
        for version in version_list:
            print("getting the latest payload of %s" % version)
            for tag in dict['tags']:
                if tag['phase'] == 'Accepted':
                    new = VersionInfo.parse(tag['name'])
                    old = VersionInfo.parse(version)
                    if new >= old:
                        if new.minor == old.minor:
                            channel = version[:-2]
                            print("The latest version of %s is: %s" %(channel,tag['name']))
                            file = "Auto-OCP-%s.txt" % version[:-2]
                            if push:
                                self.push_versions(content=tag['name'], file=file, run=run)
                            break
                        # else:
                        #     print("Not in the same Y release: %s" % new)

    def save_job_data(self, dict):
         # save it to the crrent CSV file
         with open('/tmp/prow-jobs.csv', 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            L = [dict['jobName'], dict['payload'], dict['upgrade_from'], dict['upgrade_to'], dict['time'], dict['jobID'], dict['jobURL']]
            writer.writerow(L)

    # get_github_headers func adds Github Token in case rate limit   
    def get_github_headers(self):
        token = os.getenv('GITHUB_TOKEN')
        if token:
            headers = {'Authorization': 'Bearer ' + token.strip()}
            return headers
        else:
            print('No GITHUB_TOKEN found, exit...')
            sys.exit(0)

    def get_required_jobs(self, file_path):
        # file_path = "/Users/jianzhang/goproject/src/github.com/openshift/release-tests/_releases/required-jobs.json"
        print("use file: %s" % file_path)
        if file_path is None:
            return None
        with open(file_path) as f:
            jobs = f.read()
            return json.loads(jobs)
            # print(json.loads(jobs)['amd64']['jobs'])
            # print(json.loads(jobs)['arm64']['jobs'])

    # channel means minor version, such as 4.12
    def run_required_jobs(self, channels, file_path, type = 'stable'):
        if type is None:
            type = 'stable'
        job_dict = self.get_required_jobs(file_path)
        if channels is not None and job_dict is not None:
            channel_list = channels.split(",")
            for channel in channel_list:
                print(channel)
                exist_jobs = self.search_job(None, channel)
                if channel in job_dict.keys():
                    print(channel)
                    for job in job_dict[channel]:
                        print(job)
                        for j in exist_jobs['periodics']:
                            if job in j['name'] and type in j['name']:
                                self.run_job(j['name'], None, None, None)

    # run_job func runs job by calling the API
    def run_job(self, jobName, payload, upgrade_from, upgrade_to):
        if jobName is None:
            print('Error! Please input the correct prow job name!')
        elif jobName.startswith("periodic-ci-"):
            periodicJob = jobName.strip()
        else:
            # it returns the first match job
            periodicJob = self.search_job(jobName, None)

        if periodicJob is not None:
            url = self.gangwayURL+periodicJob.strip()
            res = requests.post(url=url, json=self.get_job_data(payload, upgrade_from, upgrade_to), headers=self.get_prow_headers())
            if res.status_code == 200:
                # print(res.text)
                job_id = json.loads(res.text)["id"]
                print("Returned job id: %s" % job_id)
                self.get_job_results(job_id, jobName, payload, upgrade_from, upgrade_to)
            else:
                print("Error code: %s, reason: %s" % (res.status_code, res.reason))
        else:
            print("Warning! Couldn't find job:%s" % jobName)

    def search_job(self, jobName, ocp_version):
        print('Searching job...')
        jobURLs = 'https://api.github.com/repos/openshift/release/contents/ci-operator/jobs/openshift/openshift-tests-private/?ref=master'
        req = requests.get(url=jobURLs, timeout=3)
        if req.status_code == 200:
            file_dict = yaml.load(req.text, Loader=yaml.FullLoader)
            for file in file_dict:
                fileName = file['name'].strip()
                if ocp_version is not None and ocp_version not in fileName:
                    continue
                if fileName.endswith('.yaml') and 'periodics' in fileName:
                    print(">>>> " + fileName)
                    url = 'https://api.github.com/repos/openshift/release/contents/ci-operator/jobs/openshift/openshift-tests-private/{}?ref=master'.format(fileName)
                    res=requests.get(url=url, headers=self.get_github_headers(), timeout=3)
                    if res.status_code == 200:
                        # We have to get the git blobs when the size is very large, such as
                        # git_url = 'https://api.github.com/repos/openshift/release/git/blobs/7546acab2fdc5fcde2df8d549df1d2886fcb4efc'
                        git_url = res.json()['git_url']
                        res = requests.get(url=git_url, headers=self.get_github_headers(), timeout=3)
                        if res.status_code == 200:
                            content = base64.b64decode(res.json()['content'].replace("\n", "")).decode('utf-8')
                            job_dict = yaml.load(content, Loader=yaml.FullLoader)
                            if job_dict is None:
                                print("Warning! Couldn't get retunred JSON content when scanning %s!" % fileName)
                                continue
                            if jobName is not None:
                                for job in job_dict['periodics']:
                                    if jobName in job['name']:
                                        return job['name']
                            else:
                                return job_dict

    def query_jobs(self,url, neededJobs):
        try:
            res=requests.get(url=url, headers=self.get_github_headers(), timeout=3)
            if res.status_code == 200:
                content = base64.b64decode(res.json()['content'].replace("\n", "")).decode('utf-8')
                job_dict = yaml.load(content, Loader=yaml.FullLoader)
                for job in job_dict['tests']:
                    jobName = job['as']
                    if jobName in neededJobs['amd64']['jobs'] or jobName in neededJobs['arm64']['jobs']:
                        print(jobName)
                    else:
                        print("Warning %s is not list in the required JSON list, skip!!!" % jobName)
            else:
                print('warning:' + res.reason)

        except Exception as e:
            print(e)

    def get_job_results(self, jobID, jobName=None, payload=None, upgrade_from=None, upgrade_to=None):
        if jobID:
            req = requests.get(url=self.prowJobURL.format(jobID.strip()))
            if req.status_code == 200:
                # the returned content is not the standard JSON format so use RE instead
                # jsonData = json.loads(req.text)
                # jsonData = req.json()
                urlPattern = re.compile('.*url: (.*)\n$', re.S)
                timePattern = re.compile('.*creationTimestamp: \"(.*?)\"', re.S)
                urlList = urlPattern.findall(req.text)
                timeList = timePattern.findall(req.text)
                if len(urlList) == 1 and len(timeList) == 1:
                    jobURL = urlList[0]
                    createTime = timeList[0]
                    print(jobName, payload, jobID, createTime, jobURL)
                    dict = {
                        'jobName': jobName,
                        'payload': payload,
                        'upgrade_from': upgrade_from,
                        'upgrade_to': upgrade_to,
                        'time' : createTime,
                        'jobID' : jobID,
                        'jobURL' : jobURL
                    }
                    self.save_job_data(dict=dict)
                else:
                    print("Not found the url link or creationTimestamp...")
            else:
                raise Exception("return status code:%s reason:%s" % (req.status_code, req.reason))
        else:
            print('No job ID input, exit...')
            sys.exit(0)


    # version is OCP stable payload x.y version, such as 4.12  
    def query_files(self, version):
        neededJobs = self.get_required_jobs()
        baseURL = 'https://api.github.com/repos/openshift/release/contents/ci-operator/config/openshift/openshift-tests-private/?ref=master'
        req = requests.get(url=baseURL, timeout=3)
        if req.status_code == 200:
            file_dict = yaml.load(req.text, Loader=yaml.FullLoader)
            for file in file_dict:
                fileName = file['name'].strip()
                if fileName.endswith('.yaml') and (version in fileName):
                    if 'upgrade' in fileName:
                        # print('upgrade: ' + fileName)
                        url = self.jobURL.format(fileName)
                        self.query_jobs(url, neededJobs)
                    elif 'stable' in fileName:
                        # print('installation: ' + fileName)
                        url = self.jobURL.format(fileName)
                        self.query_jobs(url, neededJobs)
                        pass
                    else:
                        # print('others: ' + fileName)
                        pass
        else:
            print(req.reason)

    def list_jobs(self, component, branch):
        if component is None:
            component = "openshift/openshift-tests-private"
        if branch is None:
            branch = "master"
        baseURL = 'https://api.github.com/repos/openshift/release/contents/ci-operator/config/%s/?ref=%s' % (component, branch)
        req = requests.get(url=baseURL, timeout=3)
        if req.status_code == 200:
            file_dict = yaml.load(req.text, Loader=yaml.FullLoader)
            file_count = 0
            for file in file_dict:
                if file['name'].endswith('.yaml'):
                    url = self.jobURL.format(file['name'].strip())
                    print(url)
                    self.get_jobs(url)
                    file_count += 1
            print("Total file number under %s folder is:%s" % (component, str(file_count)))
        else:
            print(req.reason)
    def get_jobs(self,url):
        try:
            res=requests.get(url=url, headers=self.get_github_headers(), timeout=3)
            if res.status_code == 200:
                content = base64.b64decode(res.json()['content'].replace("\n", "")).decode('utf-8')
                job_dict = yaml.load(content, Loader=yaml.FullLoader)
                api_count = 0
                for job in job_dict['tests']:
                    api = 'true'
                    api_count += 1
                    print(job['as'] + "   " + api)
                print('Total number of api job is: ' + str(api_count))
            else:
                print('warning:' + res.reason)
        except Exception as e:
            print(e)

job = Jobs()
@click.group()
@click.version_option(package_name='job')
@click.option('--debug/--no-debug', default=False)
def cli(debug):
    """"This job tool based on Prow REST API(https://github.com/kubernetes/test-infra/issues/27824), used to handle those prow jobs."""
    click.echo('Debug mode is %s' % ('on' if debug else 'off'))

@cli.command("get_results")
@click.argument("job_id")
# @click.option('--job_id', help="The Prow job ID.")
def get_cmd(job_id):
    """Return the Prow job executed info."""
    job.get_job_results(job_id)

@cli.command("run")
@click.argument("job_name")
@click.option("--payload", help="specify a payload for e2e test, if not, it will use the latest payload from https://amd64.ocp.releases.ci.openshift.org/")
@click.option("--upgrade_from", help="specify an original payload for upgrade test.")
@click.option("--upgrade_to", help="specify a target payload for upgrade test.")
def run_cmd(job_name, payload, upgrade_from, upgrade_to):
    """Run a job and save results to /tmp/prow-jobs.csv"""
    job.run_job(job_name, payload, upgrade_from, upgrade_to)

@cli.command("list")
@click.option("--component", help="The detault is 'openshift/openshift-tests-private': https://github.com/openshift/release/tree/master/ci-operator/config/openshift/openshift-tests-private ")
@click.option("--branch", help="the master branch is as default.")
def run_cmd(component, branch):
    """List the jobs which support the API call."""
    job.list_jobs(component, branch)

@cli.command("run_required")
@click.option("--channel", help="The OCP minor version, if multi versions, comma spacing, such as 4.12,4.11")
@click.option("--file", help="a file that stores required jobs for all OCP versions.")
@click.option("--type", help="stable or nightly test")
def run_cmd(channel, file, type):
    """Run required jobs from a file"""
    job.run_required_jobs(channel, file, type)

@cli.command("get_payloads")
@click.argument("versions")
@click.option("--push", default=False, help="push the info to the https://api.github.com/repos/openshift/release-tests/contents/_releases/")
@click.option("--run", default=False, help="Run the jobs stored in the _releases/required-jobs.json file if any updates. Note that: it won't be executed if --push is False")
def run_payloads(versions, push, run):
    """Check the latest payload of each version. Use comma spacing if multi versions, such as, 4.10.0,4.11.0,4.12.0"""
    job.get_payloads(versions, push, run)

if __name__ == '__main__':
    start=time.time()
    cli()
    end=time.time()
    print('execute time cost:%.2f'%(end-start))
