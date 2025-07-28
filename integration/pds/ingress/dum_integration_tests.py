
import getpass
import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from os.path import abspath, basename, dirname, exists, join

from pkg_resources import resource_filename

from pds.ingress import __version__
from pds.ingress.util.hash_util import md5_for_path
import pds.ingress.client.pds_ingress_client as pds_ingress_client


class DumIntegrationTest(unittest.TestCase):
    test_dir = None
    scripts_dir = None
    config_dir = None
    terraform_dir = None

    @classmethod
    def setUpClass(cls):
        cls.test_dir = resource_filename(__name__, "")
        cls.scripts_dir = abspath(join(cls.test_dir, os.pardir, os.pardir, 'scripts'))
        cls.config_dir = abspath(join(cls.test_dir, os.pardir, os.pardir, 'config'))
        cls.terraform_dir = abspath(join(cls.test_dir, os.pardir, os.pardir, os.pardir, 'terraform'))

        username = getpass.getuser()

        # Start a localstack container in detached mode
        subprocess.run(["localstack", "start", "-d"], check=True)

        # Create the necessary IAM roles
        subprocess.run(
            [join(cls.scripts_dir, 'create_localstack_iam_roles.sh')],
            cwd=cls.config_dir, check=True, capture_output=True
        )

        cls.instantiate_localstack_tfvars(username)

        api_gateway_id, cognito_client_id = cls.terraform_localstack()

        cls.instantiate_dum_client_template(username, api_gateway_id, cognito_client_id)

    @classmethod
    def tearDownClass(cls):
        # Stop the localstack instance
        subprocess.run(["localstack", "stop"], check=True)

        # Remove the instantiated templates
        if exists(join(cls.terraform_dir, "localstack.tfvars")):
            os.unlink(join(cls.terraform_dir, "localstack.tfvars"))

        if exists(join(cls.config_dir, "localstack.ingress.config.ini")):
            os.unlink(join(cls.config_dir, "localstack.ingress.config.ini"))

        # Remove the now-outdated plan file
        if exists(join(cls.terraform_dir, "localstack.tfplan")):
            os.unlink(join(cls.terraform_dir, "localstack.tfplan"))

    @classmethod
    def instantiate_localstack_tfvars(cls, username):
        """Instantiate the .tfvars template used to deploy DUM to localstack"""
        with open(join(cls.config_dir, "localstack.tfvars.tmpl"), "r") as infile:
            config_contents = infile.read()

        config_contents = config_contents.replace("__USERNAME__", username)

        with open(join(cls.terraform_dir, "localstack.tfvars"), "w") as outfile:
            outfile.write(config_contents)

    @classmethod
    def terraform_localstack(cls):
        """Performs the terraform deployment of DUM on the localstack instance"""
        result = subprocess.run(["tflocal", "init"],
                       cwd=cls.terraform_dir, check=False, capture_output=True)
        assert(result.returncode == 0)
        result = subprocess.run(["tflocal", "plan", "-var-file=localstack.tfvars", "-out=localstack.tfplan", "-no-color"],
                       cwd=cls.terraform_dir, check=False, capture_output=True)
        assert (result.returncode == 0)
        subprocess.run(["tflocal", "apply", "-auto-approve", "-no-color", "localstack.tfplan"],
                       cwd=cls.terraform_dir, check=False, capture_output=True)
        assert (result.returncode == 0)

        # Get the terraform outputs we need to initialze the DUM client config
        api_gateway_id = subprocess.run(["tflocal", "output", "nucleus_dum_api_id"],
                                        cwd=cls.terraform_dir, check=True, capture_output=True).stdout.decode().strip()

        cognito_client_id = subprocess.run(["tflocal", "output", "nucleus_dum_cognito_user_pool_client_id"],
                                           cwd=cls.terraform_dir, check=True, capture_output=True).stdout.decode().strip()

        return api_gateway_id.strip('"'), cognito_client_id.strip('"')

    @classmethod
    def instantiate_dum_client_template(cls, username, api_gateway_id, cognito_client_id):
        """Instantiate the DUM client config to be used with the integration test"""
        with open(join(cls.config_dir, "localstack.ingress.config.ini.tmpl"), "r") as infile:
            config_contents = infile.read()

        config_contents = config_contents.replace("__API_GATEWAY_ID__", api_gateway_id) \
                                         .replace("__COGNITO_CLIENT_ID__", cognito_client_id) \
                                         .replace("__USERNAME__", username)

        with open(join(cls.config_dir, "localstack.ingress.config.ini"), "w") as outfile:
            outfile.write(config_contents)

    def setUp(self):
        """Create a test file with random content"""
        self.test_file = tempfile.NamedTemporaryFile(prefix="dum_", suffix=".dat", delete=False)
        subprocess.run(["dd", "if=/dev/urandom", f"of={self.test_file.name}", "bs=1M", "count=1"], check=True)

        # Calculate the md5 of the random file
        md5 = md5_for_path(self.test_file.name)

        self.test_file_hash = md5.hexdigest()
        self.test_file_last_modified_time = datetime.fromtimestamp(
            int(os.path.getmtime(self.test_file.name)), tz=timezone.utc).isoformat()

        self.empty_test_file = tempfile.NamedTemporaryFile(prefix="dum_empty_", suffix=".dat", delete=False)

    def tearDown(self):
        """Remove the test files"""
        if exists(self.test_file.name):
            os.unlink(self.test_file.name)

        if exists(self.empty_test_file.name):
            os.unlink(self.empty_test_file.name)

    def test_ingress(self):
        """Ingress integration test between DUM client and Lambda Service (localstack)"""
        # Set up a basic ingress request for a single file
        args = pds_ingress_client.setup_argparser().parse_args(
            [
                "-c",
                join(self.config_dir, "localstack.ingress.config.ini"),
                "-n",
                "sbn",
                "--prefix",
                dirname(self.test_file.name),
                "--num-threads",
                "1",
                self.test_file.name
            ]
        )


        pds_ingress_client.main(args)

        result = subprocess.run(
            ["awslocal", "s3api", "head-object", "--bucket", "pds-sbn-staging-localstack", "--key",
             f"sbn/{basename(self.test_file.name)}"],
            check=False, capture_output=True
        )

        self.assertTrue(result.returncode == 0)

        object_metadata = json.loads(result.stdout.decode().strip())

        # Test metadata assigned by S3
        self.assertEqual(int(object_metadata["ContentLength"]), os.stat(self.test_file.name).st_size)
        self.assertEqual(object_metadata['ETag'].strip('"'), self.test_file_hash)

        # Test additional metadata provided by client
        self.assertEqual(object_metadata["Metadata"]["dum_client_version"], __version__)
        self.assertEqual(object_metadata["Metadata"]["dum_service_version"], __version__)
        self.assertEqual(object_metadata["Metadata"]["last_modified"], self.test_file_last_modified_time)
        self.assertEqual(object_metadata["Metadata"]["md5"], self.test_file_hash)

        # Save the initial last modified time (relative to time of S3 upload)
        initial_s3_last_modified_time = object_metadata['LastModified']

        # Repeat transfer with same configuration, Lambda service should
        # detect that file is already present and skip overwrite
        pds_ingress_client.main(args)

        result = subprocess.run(
            ["awslocal", "s3api", "head-object", "--bucket", "pds-sbn-staging-localstack", "--key",
             f"sbn/{basename(self.test_file.name)}"],
            check=False, capture_output=True
        )

        self.assertTrue(result.returncode == 0)

        object_metadata = json.loads(result.stdout.decode().strip())

        # Object modifed time on S3 should not have changed
        self.assertEqual(object_metadata['LastModified'], initial_s3_last_modified_time)

        args.force_overwrite = True

        pds_ingress_client.main(args)

        result = subprocess.run(
            ["awslocal", "s3api", "head-object", "--bucket", "pds-sbn-staging-localstack", "--key",
             f"sbn/{basename(self.test_file.name)}"],
            check=False, capture_output=True
        )

        self.assertTrue(result.returncode == 0)

        object_metadata = json.loads(result.stdout.decode().strip())

        # With forced overwite, the S3 relative modified time should have changed,
        # but the modified time relative to local file system should not
        self.assertNotEqual(object_metadata['LastModified'], initial_s3_last_modified_time)
        self.assertEqual(object_metadata["Metadata"]["last_modified"], self.test_file_last_modified_time)

        # Test empty file transfer
        args = pds_ingress_client.setup_argparser().parse_args(
            [
                "-c",
                join(self.config_dir, "localstack.ingress.config.ini"),
                "-n",
                "sbn",
                "--prefix",
                dirname(self.test_file.name),
                "--num-threads",
                "1",
                self.empty_test_file.name
            ]
        )

        pds_ingress_client.main(args)

        result = subprocess.run(
            ["awslocal", "s3api", "head-object", "--bucket", "pds-sbn-staging-localstack", "--key",
             f"sbn/{basename(self.empty_test_file.name)}"],
            check=False, capture_output=True
        )

        self.assertTrue(result.returncode == 0)

        object_metadata = json.loads(result.stdout.decode().strip())

        self.assertEqual(int(object_metadata["ContentLength"]), 0)
