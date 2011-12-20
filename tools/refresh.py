
import ckanclient

cc = ckanclient.CkanClient(base_location="http://iatiregistry.org/api", api_key="29098b9d-a8e5-4894-b897-ab4094ce8331")
for pkg_name in cc.package_register_get():
    pkg = cc.package_entity_get(pkg_name)
    print pkg
    cc.package_entity_put(pkg)
    print cc.last_status
