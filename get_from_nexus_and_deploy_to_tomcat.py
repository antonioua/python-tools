#!/usr/bin/env python2.7


import os
import urllib2
from urllib2 import URLError, HTTPError
import re
import sys
import base64
import subprocess
import json
import ssl
import socket

# vars for nexus auth
ARTIFACT_SERVER_REPO_URL = "http://mydomain.com/nexus"
ARTIFACT_SERVER_REPOID = "war-theme-releases"
ARTIFACT_SERVER_USER = "user"
ARTIFACT_SERVER_PASS = "pass"

# vars for lf auth
APP_USER = "user"
APP_PASS = 'pass'

# vars for app_server auth
APP_SERVER_PROTO = "http://"
APP_SERVER_PORT = ":8080"
APP_SERVER_USER = "user"
APP_SERVER_PASS = "pass"

# vars for liquibase
APP_CONF_FILE = "application.conf"
REMOTE_TMP_PATH = "/tmp"
LIQUIBASE_JAR_PATH = "liquibase-core-2.0.3.jar"
MYSQL_CONNECTOR_JAR = "mysql-connector-java-5.1.34.jar"
JAVA_EXECUTABLE_BIN_PATH = "java"

app_user = "apps"
ssh_args = "-o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -q"

status = False

try:
    network_type = os.environ["ENV_NW"]
    status = True
except:
    sys.stdout.flush()
    print "ENV_NW variaable is not set"
    pass

if (status == True):
    if (network_type == "type1"):
        sys.stdout.flush()
        print network_type + " network was chosen"
        ssh_user = "user1"
        ssh_private_key_path = "id_rsa1"
    elif (network_type == "type2"):
        sys.stdout.flush()
        print network_type + " network was chosen"
        ssh_user = "user2"
        ssh_private_key_path = "id_rsa2"
    elif (network_type == "type3"):
        sys.stdout.flush()
        print network_type + " network was chosen"
        ssh_user = "user3"
        ssh_private_key_path = "id_rsa3"
else:
    sys.stdout.flush()
    print "\nInfra network was chosen\n"
    ssh_user = "user1"
    ssh_private_key_path = "id_rsa1"


def main():
    # read environment variables and check if all are set
    try:
        group_id = os.environ['PRJ_NAME']
        os.environ['TARGET_ENV']
        target_node = os.environ['TARGET_NODE'].split(',')
        wars_to_deploy = os.environ['WARS_TO_DEPLOY'].split(',')
    except NameError, ne:
        sys.stdout.flush()
        print "Variable " + "\"" + ne.message + "\"" + " is not found!"
        sys.exit(1)
    except KeyError, ke:
        sys.stdout.flush()
        print "Variable " + "\"" + ke.message + "\"" + " is not defined!"
        sys.exit(1)

    themes_status = download_themes(wars_to_deploy, group_id)
    if (themes_status == False):
        print "Download of theme file failed. Exiting..."
        sys.exit(1)

    changesets_response_dict = download_changesets(wars_to_deploy, group_id)
    if (changesets_response_dict["status"] == False):
        print "Download of cahngesets file failed. Skipping..."

    upload_theme_app_server(wars_to_deploy, target_node, changesets_response_dict["status"], changesets_response_dict["file_path"])


def download_themes(wars_to_deploy, group_id):
    # download themes to workspace
    for war in wars_to_deploy:

        war_url = ARTIFACT_SERVER_REPO_URL + "/content/repositories/" + ARTIFACT_SERVER_REPOID + "/" + group_id.lower() + "/" + war

        sys.stdout.flush()
        print "Downloading " + war_url + " ..."

        dst_war_file_name = war
        try:
            req_war = urllib2.Request(war_url)
            base64String3 = base64.encodestring('%s:%s' % (ARTIFACT_SERVER_USER, ARTIFACT_SERVER_PASS)).replace('\n', '')
            req_war.add_header("Authorization", "Basic %s" % base64String3)
            resp_war = urllib2.urlopen(req_war)
            war_data = resp_war.read()

            with open(dst_war_file_name, "wb") as war_file:
                war_file.write(war_data)

        except HTTPError, e:
            sys.stdout.flush()
            print "HTTP Error:", e.code, war_url
            downloaded = False
            return downloaded

        except URLError, e:
            sys.stdout.flush()
            print "URL Error:", e.reason, war_url
            downloaded = False
            return downloaded

    sys.stdout.flush()
    print "Done.\n"
    downloaded = True
    return downloaded


def download_changesets(wars_to_deploy, group_id):
    # download changesets to workspace
    war_build_number = re.findall('\d+', wars_to_deploy[0])
    # print war_build_number
    changeset_file_name = group_id.lower() + "." + ''.join(war_build_number) + ".xml.tar"
    changeset_url = ARTIFACT_SERVER_REPO_URL + "/content/repositories/" + ARTIFACT_SERVER_REPOID + "/" + group_id.lower() + "/" + changeset_file_name

    try:
        sys.stdout.flush()
        print "Downloading " + changeset_url + " ..."
        req_cahngeset = urllib2.Request(changeset_url)
        base64String4 = base64.encodestring('%s:%s' % (ARTIFACT_SERVER_USER, ARTIFACT_SERVER_PASS)).replace('\n', '')
        req_cahngeset.add_header("Authorization", "Basic %s" % base64String4)
        resp_cahngeset = urllib2.urlopen(req_cahngeset)
        changeset_data = resp_cahngeset.read()
        with open(changeset_file_name, "wb") as changeset_file:
            changeset_file.write(changeset_data)

        sys.stdout.flush()
        print "Done.\n"
        downloaded = True
        return {"status": downloaded, "file_path": changeset_file_name}

    except HTTPError, e:
        sys.stdout.flush()
        print "HTTP Error:", e.code, changeset_url
        downloaded = False
        return {"status": downloaded, "file_path": changeset_file_name}

    except URLError, e:
        sys.stdout.flush()
        print "URL Error:", e.reason, changeset_url
        downloaded = False
        return {"status": downloaded, "file_path": changeset_file_name}


def upload_theme_app_server(wars_to_deploy, target_node, changesets_status, changeset_file_name):
    # uploading themes to app_server
    for vm in target_node:
        sys.stdout.flush()
        print "Now deploying to " + APP_SERVER_PROTO + vm + APP_SERVER_PORT + "\n"

        # prepare ssh cmd for the below cmds
        ssh_to_host_cmd_general = "ssh {0} -t -i {1} {2}@{3} ".format(ssh_args, ssh_private_key_path, ssh_user, vm)

        dict_deployed_themes = {}

        for war in wars_to_deploy:
            sys.stdout.flush()
            print "\nDeploying " + war + " ..." + "\n"
            war_file_content = open(war, "rb").read()

            theme_to_arr = war.split(".")
            theme_name = theme_to_arr[0]
            theme_build_id = theme_to_arr[1]
            dict_deployed_themes[theme_name] = theme_build_id

            reqUrl = APP_SERVER_PROTO + vm + APP_SERVER_PORT + "/manager/text/deploy?path=/" + theme_name + "&update=true"
            base64String = base64.encodestring("%s:%s" % (APP_SERVER_USER, APP_SERVER_PASS)).replace("\n", "")
            deployReq = urllib2.Request(reqUrl, data=war_file_content)
            deployReq.add_header("Content-Type", "application/octet-stream")
            deployReq.add_header("Authorization", "Basic %s" % base64String)
            # print deployReq.headers
            deployReq.get_method = lambda: "PUT"

            # Proxy section
            proxy_host = "172.29.50.100"
            proxy_port = "8080"

            # disable ssl check
            sys.stdout.flush()
            print "Disable SSL check"
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            # add proxy
            proxy = urllib2.ProxyHandler({"https": "{0}:{1}".format(proxy_host, proxy_port)})
            opener = urllib2.build_opener(urllib2.HTTPSHandler(context=ctx), proxy)
            urllib2.install_opener(opener)
            # End of proxy section

            try:
                response = urllib2.urlopen(deployReq).read()
                print response
            except urllib2.HTTPError, err:
                if err.code == "404":
                    sys.stdout.flush()
                    print "404. Page not found!"
                    sys.exit(1)
                elif err.code == "403":
                    sys.stdout.flush()
                    print "403. Access denied!"
                    sys.exit(1)
                else:
                    sys.stdout.flush()
                    print "Something went wrong! Erorr code", err.code
                    sys.exit(1)
            except urllib2.URLError, err:
                sys.stdout.flush()
                print "Something went wrong! Reason: ", err.reason
                sys.exit(1)

            #sys.stdout.flush()
            #print response.replace('\n', '')

            # now let's check if app_server returned OK
            arr1 = response.split(" ")
            if arr1[0] != "OK":
                sys.stdout.flush()
                print "Something went wrong, response from app_server: " + arr1[0]
                sys.exit(1)

            # Liquebase: hack for do not apply changesets on each war deploy
            if wars_to_deploy.index(war) == 0:

                # Liquebase: get mysql connection data and run liquibase
                if (changesets_status == True):

                    # applying changesets to current node
                    sys.stdout.flush()
                    print ("\nGathering mysql db conenction data ...")

                    # get mysql connection data
                    db_conn_data_dict = get_db_connection_data_from_vm(vm, ssh_to_host_cmd_general)

                    # run liquibase
                    run_liquibase(vm, ssh_to_host_cmd_general, db_conn_data_dict, changeset_file_name)
                else:
                    sys.stdout.flush()
                    print "Skipping liquibase run..."

        # Modify file.json file on vm after theme was deployed
        # we decided to modify the back-end root file.json file by adding a theme name if such not exist,
        # e.g "Deployed_Themes": ["theme1", "theme2"]

        file.json_full_url = APP_SERVER_PROTO + vm + APP_SERVER_PORT + "/html/file.json"
        file_status_on_remote = check_file_on_remote(file.json_full_url)

        if (file_status_on_remote == True):
            sys.stdout.flush()
            print "File exist."
            modify_file.json_file(vm, ssh_to_host_cmd_general, dict_deployed_themes)
        else:
            sys.stdout.flush()
            print "File not found " + file.json_full_url
            print "Skipping..."

        # All wars for certain node/vm are deployed now

        # Now starting the clear cluster cache on vm/node, otherwise changes will not take affect
        clear_product_cluster_cache(vm)


def get_db_connection_data_from_vm(vm, ssh_to_host_cmd_general):
    # get db hostname
    grep_host = " \" sudo su - " + app_user + " -c ' cat {0} | grep \\\"host = \\\" -m 1 | sed -e \\\"s/.* = //g\\\" ' \" ".format(
        APP_CONF_FILE)
    get_host_cmd = ssh_to_host_cmd_general + grep_host
    proc = subprocess.Popen(get_host_cmd, stdout=subprocess.PIPE, shell=True)
    (stdout, stderr) = proc.communicate()
    exit_code = proc.wait()
    host_value = stdout.replace('\r\n', '')

    # get db name
    grep_db_name = " \" sudo su - " + app_user + " -c ' cat {0} | grep \\\"name = \\\" -m 1 | sed -e \\\"s/.* = //g\\\" ' \" ".format(
        APP_CONF_FILE)
    get_db_name_cmd = ssh_to_host_cmd_general + grep_db_name
    proc = subprocess.Popen(get_db_name_cmd, stdout=subprocess.PIPE, shell=True)
    (stdout, stderr) = proc.communicate()
    exit_code = proc.wait()
    db_name_value = stdout.replace('\r\n', '')

    # get db user
    grep_db_user = " \" sudo su - " + app_user + " -c ' cat {0} | grep \\\"user = \\\" -m 1 | sed -e \\\"s/.* = //g\\\" ' \" ".format(
        APP_CONF_FILE)
    get_db_user_cmd = ssh_to_host_cmd_general + grep_db_user
    proc = subprocess.Popen(get_db_user_cmd, stdout=subprocess.PIPE, shell=True)
    (stdout, stderr) = proc.communicate()
    exit_code = proc.wait()
    db_user_value = stdout.replace('\r\n', '')

    # get db pass
    grep_db_pass = " \" sudo su - " + app_user + " -c ' cat {0} | grep \\\"password = \\\" -m 1 | sed -e \\\"s/.* = //g\\\" ' \" ".format(
        APP_CONF_FILE)
    get_db_pass_cmd = ssh_to_host_cmd_general + grep_db_pass
    proc = subprocess.Popen(get_db_pass_cmd, stdout=subprocess.PIPE, shell=True)
    (stdout, stderr) = proc.communicate()
    exit_code = proc.wait()
    db_pass_value = stdout.replace('\r\n', '')
    # print db_pass_value

    return {"db_host": host_value, "db_name": db_name_value, "db_user": db_user_value, "db_pass": db_pass_value}


def run_liquibase(vm, ssh_to_host_cmd_general, db_conn_data_dict, changeset_file_name):
    # generate liquibase.properties file
    LIQUIBASE_PRP_FILE = "liquibase.properties"
    USERNAME_TO_CONF = "username: " + db_conn_data_dict["db_user"].replace('"', '')
    PASSWORD_TO_CONF = "password: " + db_conn_data_dict["db_pass"].replace('"', '')
    host_value = db_conn_data_dict["db_host"].replace('\n', '')
    URL_TO_CONF = "url: jdbc:mysql://{0}:{1}/{2}".format(host_value.replace('"', ''), '3306',
                                                         db_conn_data_dict["db_name"].replace('"', ''))
    CONF = [URL_TO_CONF, USERNAME_TO_CONF, PASSWORD_TO_CONF]
    with open(LIQUIBASE_PRP_FILE, 'w') as liquibase_conf:
        i = 0
        for i in CONF:
            liquibase_conf.write(i)

    # copy liquibase.properties to vm
    sys.stdout.flush()
    print "\nCopying liquibase properties file " + LIQUIBASE_PRP_FILE + " to " + vm + " ..."
    scp_liquibase_properties_to_host_cmd = "scp {0} -i {1} {2} {3}@{4}:{5}".format(
        ssh_args, ssh_private_key_path, LIQUIBASE_PRP_FILE, ssh_user, vm, REMOTE_TMP_PATH)
    proc = subprocess.Popen(scp_liquibase_properties_to_host_cmd, stdout=subprocess.PIPE, shell=True)
    sys.stdout.flush()
    (stdout, stderr) = proc.communicate()
    exit_code = proc.wait()

    # delete temporary liquibase.properties from local host
    os.remove(LIQUIBASE_PRP_FILE)

    # copy changesets file to vm
    sys.stdout.flush()
    print "\nCopying changeset file " + changeset_file_name + " to " + vm + " ..."
    scp_changesets_to_host_cmd = "scp {0} -i {1} {2} {3}@{4}:{5}".format(
        ssh_args, ssh_private_key_path, changeset_file_name, ssh_user, vm, REMOTE_TMP_PATH)
    proc = subprocess.Popen(scp_changesets_to_host_cmd, stdout=subprocess.PIPE, shell=True)
    sys.stdout.flush()
    (stdout, stderr) = proc.communicate()
    exit_code = proc.wait()

    # preapre changesets for execution
    sys.stdout.flush()
    print "Preparing changesets for execution"
    prep_changesets_for_exec_cmd = ssh_to_host_cmd_general + \
                                   " \"sudo su - root -c 'mkdir -p {0}/changelogs; " \
                                   "mv {0}/{1} {0}/changelogs/{1};" \
                                   "cd {0}/changelogs/ && tar xvf {1}' \" ".format(REMOTE_TMP_PATH, changeset_file_name)
    proc = subprocess.Popen(prep_changesets_for_exec_cmd, stdout=subprocess.PIPE, shell=True)
    (stdout, stderr) = proc.communicate()
    exit_code = proc.wait()

    # executing liquibase cmd
    sys.stdout.flush()
    print "Executing liquibase " + vm + " ..."
    #CHANGESETS_DST_FULL_PATH = REMOTE_TMP_PATH + "/" + changeset_file_name
    LIQUIBASE_CONF_FILE = REMOTE_TMP_PATH + "/" + LIQUIBASE_PRP_FILE
    sys.stdout.flush()
    run_liquibase_cmd = ssh_to_host_cmd_general + \
                        " \"sudo su - root -c 'cd {0}; " \
                        "{1} -jar {2} --classpath={3} " \
                        "--driver=com.mysql.jdbc.Driver --changeLogFile=changelogs/changesets.xml " \
                        "--defaultsFile={4} update' \" ".format(REMOTE_TMP_PATH,
                                                                JAVA_EXECUTABLE_BIN_PATH,
                                                                LIQUIBASE_JAR_PATH,
                                                                MYSQL_CONNECTOR_JAR,
                                                                LIQUIBASE_CONF_FILE)

    #sys.stdout.flush()
    #print "Running cmd: " + run_liquibase_cmd
    proc = subprocess.Popen(run_liquibase_cmd, stdout=subprocess.PIPE, shell=True)
    (stdout, stderr) = proc.communicate()
    exit_code = proc.wait()

    sys.stdout.flush()
    print "Cleaning tmp changeset files..."
    # Clean up: clean copied changesets and liquebase files from remote temp dir
    if REMOTE_TMP_PATH:
        rm_copied_changeset_file_on_vm_cmd = ssh_to_host_cmd_general + " \" sudo su - root -c ' rm -rf {0}/changelogs/*.tar {0}/changelogs/*.xml {0}/{1}' \" ".format(
            REMOTE_TMP_PATH, LIQUIBASE_PRP_FILE)
        proc = subprocess.Popen(rm_copied_changeset_file_on_vm_cmd, stdout=subprocess.PIPE, shell=True)
        (stdout, stderr) = proc.communicate()
        exit_code = proc.wait()
    print "Success."


def modify_file.json_file(vm, ssh_to_host_cmd_general, dict_deployed_themes):
    # Modify root file.json if the env was deployed with war
    VERSION_JSON_FULL_PATH = "/opt/111/111/111/1111/html/file.json"

    if VERSION_JSON_FULL_PATH:
        sys.stdout.flush()
        print "Taking file over SSH.."
        read_file.json_file_cmd = ssh_to_host_cmd_general + " \" sudo su - {0} -c ' cat {1} ' \" ".format(
            app_user, VERSION_JSON_FULL_PATH)
        proc = subprocess.Popen(read_file.json_file_cmd, stdout=subprocess.PIPE, shell=True)
        (stdout_file.json_file_cmd, stderr) = proc.communicate()
        exit_code = proc.wait()

        # if the ssh cmd was successful
        if exit_code == 0:
            sys.stdout.flush()
            print "Success."
            ###sys.stdout.flush()
            ###print str(stdout_file.json_file_cmd)
            json_decoded = json.loads(stdout_file.json_file_cmd)

            # remove nonactual values from root file.json file if env was deployed with war
            try:
                # del file.json_obj["WPL_Git_Log"]
                del json_decoded["Product_Version"]
            except KeyError:
                pass

            # add to root file.json file the state if this vm was deployed with war
            #json_decoded["State"] = "Last deployed with WAR"

            #dic_of_exisitng_themes = {}
            # Check if file.json already has 'Deployed_Themes' prp
            if ("Deployed_Themes" in json_decoded):
                dic_of_exisitng_themes = json_decoded["Deployed_Themes"]

                # Avoid type erorrs when changing Deployed_Themes from list to dictionary
                if not isinstance(dic_of_exisitng_themes, dict): dic_of_exisitng_themes = {}

                for deployed_theme in dict_deployed_themes:
                    dic_of_exisitng_themes[deployed_theme] = dict_deployed_themes[deployed_theme]

                json_decoded["Deployed_Themes"] = dic_of_exisitng_themes
            else:
                # if hasn't 'Deployed_Themes' prp then add it
                json_decoded["Deployed_Themes"] = dict_deployed_themes


            # encode to json object and save to file
            with open('file.json', 'w') as versionJsonFile:
                json.dump(json_decoded, versionJsonFile, sort_keys=False, indent=4)

            sys.stdout.flush()
            print "Changing root file.json file on vm..."

            # send to remote tmp dir
            scp_to_remote_cmd = "scp -i {0} {1} {2}@{3}:{4}/".format(
                ssh_private_key_path, "file.json", ssh_user, vm, REMOTE_TMP_PATH)
            proc = subprocess.Popen(scp_to_remote_cmd, stdout=subprocess.PIPE, shell=True)
            (stdout, stderr) = proc.communicate()
            exit_code = proc.wait()

            if (exit_code == 0):
                sys.stdout.flush()
                print "Success.\n"
            else:
                sys.stdout.flush()
                "Failed!\n"

            # move on remote and set app's permissions
            move_and_chown_cmd = ssh_to_host_cmd_general + " \" sudo su - root -c ' mv {0}/file.json {1}; chown {2} {1} ' \" ".format(
                REMOTE_TMP_PATH, VERSION_JSON_FULL_PATH, app_user)
            proc = subprocess.Popen(move_and_chown_cmd, stdout=subprocess.PIPE, shell=True)
            (stdout, stderr) = proc.communicate()
            exit_code = proc.wait()

        else:
            sys.stdout.flush()
            print "\nSSH was unsuccessful. Exit code: " + str(exit_code)
            print "Root file.json won't be modified."


def clear_product_cluster_cache(vm):
    sys.stdout.flush()
    print "Clearing cluster cache..."
    requrl2 = APP_SERVER_PROTO + vm + APP_SERVER_PORT + "/api/111/111/111"
    clearClCacheReq = urllib2.Request(requrl2)
    base64String2 = base64.encodestring("{0}:{1}".format(APP_USER, APP_PASS)).replace("\n", "")
    clearClCacheReq.add_header("Authorization", "Basic {0}".format(base64String2))
    try:
        response2 = urllib2.urlopen(clearClCacheReq).read()
        sys.stdout.flush()
        print "Success.\n"
    except urllib2.HTTPError, err:
        if err.code == "404":
            sys.stdout.flush()
            print "404. Page not found!\n"
        elif err.code == "403":
            sys.stdout.flush()
            print "403. Access denied!\n"
        else:
            sys.stdout.flush()
            print "Something went wrong! Erorr code", err.code
            print "API IS TURNED OFF\n" \
                  "So please clear liferay's cluster cache manualy via control panel if needed.\n"

    except (urllib2.URLError, NameError) as err:
        sys.stdout.flush()
        print "Something went wrong! Reason: ", err.reason
        print "\n"


def check_file_on_remote(url):
    sys.stdout.flush()
    print "Checking file " + url + " ..."

    req = urllib2.Request(url)
    try:
        response = urllib2.urlopen(req)
        status = True
    except urllib2.HTTPError, err:
        sys.stdout.flush()
        print err.code
        status = False
    except urllib2.URLError, e:
        sys.stdout.flush()
        print "There was an error: %r".format(e)
        status = False
    except socket.timeout, e:
        sys.stdout.flush()
        print "There was an error: %r".format(e)
        status = False

    return status



if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print "Interrupted by user."
        sys.exit(0)
