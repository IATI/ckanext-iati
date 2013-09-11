BEGIN;

DELETE FROM package_extra_revision WHERE key = 'publishertype';
DELETE FROM package_extra_revision WHERE key = 'publisher_organization_type';
DELETE FROM package_extra_revision WHERE key = 'publisher_country';
DELETE FROM package_extra_revision WHERE key = 'publisher_iati_id';

DELETE FROM package_extra WHERE key = 'publishertype';
DELETE FROM package_extra WHERE key = 'publisher_organization_type';
DELETE FROM package_extra WHERE key = 'publisher_country';
DELETE FROM package_extra WHERE key = 'publisher_iati_id';

DELETE FROM package_extra_revision WHERE key LIKE 'iati:preview%'; 
DELETE FROM package_extra WHERE key LIKE 'iati:preview%'; 

COMMIT;

