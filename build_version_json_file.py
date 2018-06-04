#!/usr/bin/env python2.7


import json
import subprocess
import datetime
import time
import sys
import re
import argparse
import os.path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bn", dest="build_number", help="build number", required=True) #build_number
    parser.add_argument("--pd", dest="project_dir", help="project root dir", required=True) #project_dir
    parser.add_argument("--pn", dest="project_name", help=" projecct name", required=True) #project_name
    parser.add_argument("--vr", dest="vcs_ref", help="version control system reference", required=True) #vcs_ref
    parser.add_argument("--bt", dest="build_type", help="build type", choices=("rpm", "war"), required=True)
    parser.add_argument("--pv", dest="platform_version", help="platform version", choices=("wpl2", "wpl3"), required=True)
    parser.add_argument("--validate-tag", dest="")
    args = parser.parse_args()

    gen_version_json(args.build_number,
                     args.project_dir,
                     args.project_name,
                     args.vcs_ref,
                     args.build_type,
                     args.platform_version)


def gen_version_json(build_number, project_dir, project_name, vcs_ref, build_type, platform_version):
    # generate base json obj
    dict_obj = {
        "Node_FQDN": "PORTAL_VM_HOSTNAME",
        "Package_Name": "",
        "Build_Number": "",
        "Prj_Version": "",
        "WPL_Version": "",
        "Built_From": "",
        "Build_Created": "",
        "WPL_Git_Log": {},
        "Prj_Themes" : []
    }

    dict_obj["Build_Number"] = build_number
    dict_obj["Built_From"] = vcs_ref

    # get last annotated tag
    last_annotated_tag_cmd = "git --git-dir={0}/.git describe --abbrev=0 --tags".format(project_dir)

    try:
        proc = subprocess.Popen(last_annotated_tag_cmd, stdout=subprocess.PIPE, shell=True)
        (stdout, stderr) = proc.communicate()
        exit_code = proc.wait()
        last_annotated_tag = stdout
    except subprocess.CalledProcessError as e:
        print "Git tag command failed with an error: " + str(e.output)
        print "Please check if you have tags in you repo."
        sys.exit(1)

    # Validate: check if last annotated tag matches our naming policy
    if (bool(re.match("^(?:\d{1,2}\.){1,3}\d{1,2}(?:-(?:\d{1,2}\.){3}\d{1,2})?$", last_annotated_tag)) == True and exit_code == 0):
        last_annotated_tag = last_annotated_tag.replace('\n', '')
        dict_obj["Prj_Version"] = last_annotated_tag
    else:
        print("Git tag validation failed! \n" +
              "Invalid tag: " + last_annotated_tag.replace('\n', '') +
              "\nPlease follow manual https://confluence.playtech.corp/display/PTL/MWS+Git+Style+Guide to fix your tag name" +
              "\nExample:\n" +
              "$ git tag -a 1.0.0-17.9.4.0 -m \"new version\" ")
        sys.exit(1)

    now = datetime.datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M") + " " + time.tzname[1]
    dict_obj["Build_Created"] = timestamp

    if build_type == "war": # don't get rpm name for war build job
        pkg_name = 'war'
        dict_obj["Package_Name"] = pkg_name
        #dict_obj["State"] = "Last deployed with WAR"
    elif build_type == "rpm":
        # building rpm name
        pkg_name = 'pt_mws_portal-{0}.{1}-{2}.noarch.rpm'.format(last_annotated_tag, build_number, project_name.lower())
        dict_obj["Package_Name"] = pkg_name
        #dict_obj["State"] = "Last deployed with RPM"
    else:
        print "ERROR: no --bt, build_type argument was given. Please specify."
        sys.exit(1)

    # getting last N commits ordered by date
    gitLastNcommitsCmdPart1 = "git --git-dir={0}/.git log -n30 ".format(project_dir)
    gitLastNcommitsCmdPart2 = "--pretty=format:\"%at %ad | %H | %s%d [%an]\" --date-order | sort -r -n -k1 | cut -f2,3,4,5,6,8-150 -d\" \" "
    gitLastNcommitsCmdPartResult = gitLastNcommitsCmdPart1 + gitLastNcommitsCmdPart2
    proc = subprocess.Popen(gitLastNcommitsCmdPartResult, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    (stdout, stderr) = proc.communicate()
    exit_code = proc.wait()

    # write each commit into array
    arrOfCommits = stdout.split("\n")

    obj_commits = {}

    i = 0
    for commitValue in arrOfCommits:
        i = i + 1
        obj_commits[i] = commitValue

    # remove last index from dictionary, it is always an empty value due to shell cmd output
    obj_commits.pop(i)
    dict_obj["WPL_Git_Log"] = obj_commits


    if platform_version == "wpl2": # if wpl2 job then core version located in gradle.wpl.properties file
        dict_obj = gen_wpl2_json(dict_obj, project_dir)
    elif platform_version == "wpl3":
        dict_obj = gen_wpl3_json(dict_obj, project_dir, last_annotated_tag)
    elif platform_version == "war":
        dict_obj = gen_wpl3_json(dict_obj, project_dir)
    else:
        print("platform_version is not sppecified.")
        sys.exit(1)

    # encode to json object and save to file
    with open('version.json', 'w') as versionJsonFile:
        json.dump(dict_obj, versionJsonFile, sort_keys=False, indent=4)

    # print json.dumps(dict_obj, sort_keys=False, indent=4)


def gen_wpl3_json(dict_obj, project_dir, last_annotated_tag):

    # wpl core 17.12 - 18.X files
    #prj_json_file_path = project_dir + "/" + "misc/fe-scripts/config/prj.json"
    #core_json_file_path = project_dir + "/" + "misc/fe-scripts/config/core.json"
    files_to_parse = ["misc/fe-scripts/config/prj.json",
                      "misc/fe-scripts/config/core.json",
                      "scripts/config/prj.json",
                      "scripts/config/core.json"
                      ]

    # wpl core 16.X - 17.X files
    config_dev_json_file_path = project_dir + "/" + "portlets/some-dir/config.dev.json"
    config_env_json_file_path = project_dir + "/" + "portlets/some-dir/config.env.json"

    # set marker
    file_found = False

    # try to read and get values
    for file in files_to_parse:
        relative_file_path = project_dir + "/" + file
        print "Reading " + relative_file_path

        if os.path.exists(relative_file_path):
            print "The file " + file + " exists, trying to take values from it"

            with open(relative_file_path) as f:
                json_decoded = json.load(f)

            # check if the required keys exists inside the json object
            if (("buildVersion" in json_decoded) and ("themes" in json_decoded)):
                dict_obj["WPL_Version"] = json_decoded["buildVersion"]
                dict_obj["Prj_Themes"] = json_decoded["themes"]
                print "Success"
                break # the required keys were found, exiting from thee loop
            else:
                print "Required keys are not exists in file"

            file_found = True
        else:
            print "File not found."


    # try to get values from config_dev_json_file_path
    if os.path.exists(config_dev_json_file_path):

        print "The file " + config_dev_json_file_path + " exists, trying to take values from it"

        with open(config_dev_json_file_path) as f:
            json_decoded = json.load(f)

        # check if the required keys exists inside the json object
        if ("buildVersion" in json_decoded):
            dict_obj["WPL_Version"] = json_decoded["buildVersion"]
            print "Success"
        else:
            print "Required keys are not exists in file"

        file_found = True


    # try to get values from config_env_json_file_path
    if os.path.exists(config_env_json_file_path):

        print "The file " + config_env_json_file_path + " exists, trying to take values from it"

        with open(config_env_json_file_path) as f:
            json_decoded = json.load(f)

        # check if the required keys exists inside the json object
        if ("themes" in json_decoded):
            dict_obj["Prj_Themes"] = json_decoded["themes"]
            print "Success"
        else:
            print "Required keys are not exists in file"

        file_found = True

    # if no files were found in above steps then this is new core back-end 18.2+
    if (file_found == False):
        print "This is new core back-end repo. Getting WPL_Version from last annotated tag."
        dict_obj["WPL_Version"] = last_annotated_tag

        try:
            del dict_obj["Prj_Version"]
            del dict_obj["Prj_Themes"]
        except KeyError:
            pass

        print "Success"


    return dict_obj


def gen_wpl2_json(dict_obj, project_dir):
    # reading wpl core version from gradle.wpl.properties
    with open('{0}/gradle.wpl.properties'.format(project_dir)) as txt_file:
        for line in txt_file:
            line = re.findall(r'version=.*', line)
            if line:
                wpl_core_version = line[0].split("=")[1]
    wpl_core_version_final = wpl_core_version.split("-")[0] + wpl_core_version.split("-")[1]
    dict_obj["WPL_Version"] = wpl_core_version_final
    print "Success"

    return dict_obj


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print "Interrupted by user."
        sys.exit(0)
