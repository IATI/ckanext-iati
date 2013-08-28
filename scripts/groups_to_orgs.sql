
UPDATE "group" SET type = 'organization';
UPDATE group_revision SET type = 'organization';

UPDATE "group" SET is_organization = True;
UPDATE group_revision SET is_organization = True;

UPDATE package p SET owner_org = m.group_id FROM member m WHERE p.id = m.table_id;
UPDATE package_revision p SET owner_org = m.group_id FROM member m WHERE p.id = m.table_id;

--- Don't forget to run users_to_members.py to set up the orgs members correctly

