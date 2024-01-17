import sys
import json
import configparser

from sqlalchemy import create_engine
import requests

HOST = 'localhost:5000'
API_KEY = 'xxx'

ACTION_URL_CREATE_MEMBER = 'http://{host}/api/action/member_create'.format(host=HOST)


def go(conf_path):
    config = configparser.SafeConfigParser()
    config.read(conf_path)

    conn = create_engine(config.get('app:main', 'sqlalchemy.url')).connect()
    sql = '''
SELECT g.id AS group_id, g.name as group_name, u.id AS user_id, u.name as user_name, ur.role AS capacity
FROM "group" g JOIN group_role gr
    ON g.id = gr.group_id
    JOIN user_object_role ur
    ON gr.user_object_role_id = ur.id
    JOIN "user" u
    ON ur.user_id = u.id
WHERE ur.context = 'Group'
    AND g.state != 'deleted'
    AND u.name != 'visitor' AND u.name != 'logged_in'
    AND u.sysadmin IS FALSE
    AND (ur.role = 'admin' OR ur.role = 'editor')
ORDER BY u.id
'''
    results = conn.execute(sql)

    headers = {'Content-type': 'application/json', 'Authorization': API_KEY}

    for row in results:
        # http://docs.ckan.org/en/latest/api.html#ckan.logic.action.create.member_create
        data = {
            'id': row['group_id'],
            'object': row['user_id'],
            'object_type': 'user',
            'capacity': row['capacity']
        }

        r = requests.post(ACTION_URL_CREATE_MEMBER,
                     data=json.dumps(data), headers=headers)

        if r.status_code != 200:
            print(r.status_code)
            print(r.content)
            continue
        
        print('Added user "{0}" as a member of org "{1}" with capacity "{2}"'.format(
                row['user_name'], row['group_name'], row['capacity']))
        


if __name__ == '__main__':
    if len(sys.argv) <= 1:
        print('Please provide path to CKAN ini file')
        sys.exit(1)
    go(sys.argv[1])
    

