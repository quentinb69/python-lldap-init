# From https://github.com/lldap/lldap/issues/654#issuecomment-1694251863
import subprocess
import json
import os

from requests import Session
from qlient.http import HTTPBackend, HTTPClient, Fields

ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', "/config/admin_password")
CONFIG_FILE = os.environ.get('CONFIG_FILE', "/config/config_file.json")
# CONFIG = {
#     "admin_username": "",
#     "ldap_url": "",
#     "web_url": "",
#     "base_dn": "",
#     "seed": {
#         "groups": [""],
#         "users": [
#             {
#                 "id": "",
#                 "email": "",
#                 "displayName": "",
#                 "groups": [""],
#                 "password_file": "",
#             },
#         ],
#     }
# }

# load configuration
with open(CONFIG_FILE) as config_file:
    CONFIG = json.load(config_file)

admin_password_file = ADMIN_PASSWORD
admin_username = CONFIG["admin_username"]
ldap_url = CONFIG["ldap_url"]
web_url = CONFIG["web_url"]
base_dn = CONFIG["base_dn"]
groups = CONFIG["seed"].get("groups", [])
users = CONFIG["seed"].get("users", [])

# prepare session
session = Session()
with open(admin_password_file, "r") as f:
    admin_password = f.read()
jwt_token = session.post(url=f'{web_url}/auth/simple/login', json={
    "username": admin_username,
    "password": admin_password,
}).json()["token"]
admin_password = ""
session.headers["Authorization"] = f"Bearer {jwt_token}"
client = HTTPClient(HTTPBackend(f'{web_url}/api/graphql', session=session))

# set structures for graphQL
GROUP_FIELDS = Fields("id", "displayName")
USER_FIELDS = Fields("id", "email", "displayName", groups=GROUP_FIELDS)

# get groups and users infos
existing_groups = client.query.groups(GROUP_FIELDS).data["groups"]
existing_groups_map = {group["displayName"]
    : group for group in existing_groups}
existing_users = client.query.users(USER_FIELDS).data["users"]
existing_users_map = {user["id"]: user for user in existing_users}

### FUNCTIONS START ###


def create_user(user_original):
    user = user_original.copy()
    del user_original
    groups = user.pop("groups", [])
    password_file = user.pop("password_file")

    # create user
    req = client.mutation.createUser(user=user, _fields=USER_FIELDS)
    assert req.errors is None, req.raw

    # add to groups
    for group in groups:
        req = client.mutation.addUserToGroup(
            userId=user["id"], groupId=group["id"])
        assert req.errors is None, req.raw

    # set password
    ret = subprocess.run([
        "ldappasswd",
        "-x",
        "-H", ldap_url,
        "-D", "uid=" + admin_username + ",ou=people," + base_dn,
        "-y", admin_password_file,
        "-W", "uid=" + user["id"] + ",ou=people," + base_dn,
        "-T", password_file
    ], capture_output=True)
    ret.check_returncode()
    print("\tCreated user '{}'".format(user["id"]))
### FUNCTIONS END ###


# create groups
for must_exist_group in sorted(groups):
    if must_exist_group not in existing_groups_map:
        print(f"Group '{must_exist_group}' does not exist, creating...")
        group = client.mutation.createGroup(
            name=must_exist_group, _fields=GROUP_FIELDS).data["createGroup"]
        existing_groups_map[must_exist_group] = group
        print(f"\tCreated group '{must_exist_group}'.")
    else:
        print(f"Group '{must_exist_group}' exists, skipping")

# create users
for must_exist_user in sorted(users, key=lambda x: x["id"]):
    must_exist_user_id = must_exist_user["id"]

    # Seed file groups is just a list of names, API returns id + displayName
    # TODO: This modifies the SEED inplace
    must_exist_user["groups"][:] = [
        existing_groups_map[group_name] for group_name in must_exist_user["groups"]
    ]

    if must_exist_user_id not in existing_users_map:
        print(f"User '{must_exist_user_id}' does not exist, creating...")
        create_user(must_exist_user)

    else:
        print(f"User '{must_exist_user_id}' exists, skipping")

# ldapsearch -x -LLL -H ldap://127.0.0.1:3890 -b dc=example,dc=com -D "uid=admin,ou=people,dc=example,dc=com" -W
# ldapadd -x -H ldap://127.0.0.1:3890 -D "uid=admin,ou=people,dc=example,dc=com" -W -f ldap.ldif
# ldappasswd -x -H ldap://127.0.0.1:3890 -D "uid=admin,ou=people,dc=example,dc=com" -W "uid=test3,ou=people,dc=example,dc=com" -s test1234
# ldappasswd -x -H ldap://localhost:3890 -D uid=admin,ou=people,dc=example,dc=com -y ./admin_password_file -W uid=server_user_b,ou=people,dc=example,dc=com -T ./pass_a

# dn: uid=test3,ou=people,dc=example,dc=com
# objectclass: inetOrgPerson
# objectclass: posixAccount
# objectclass: mailAccount
# objectclass: person
# uid: test3
# mail: test3@test
# cn: test3
# userPassword: new-password
