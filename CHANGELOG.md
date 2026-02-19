# Changelog

## [«unknown»](https://github.com/NASA-PDS/data-upload-manager/tree/«unknown») (2026-02-19)

[Full Changelog](https://github.com/NASA-PDS/data-upload-manager/compare/v2.3.0...«unknown»)

**Requirements:**

- As a data provider, I want to skip following symlinks during ingress [\#340](https://github.com/NASA-PDS/data-upload-manager/issues/340)

**Defects:**

- DUM client MD5 hash generation does not work on FIPS-enabled systems [\#337](https://github.com/NASA-PDS/data-upload-manager/issues/337) [[s.high](https://github.com/NASA-PDS/data-upload-manager/labels/s.high)]
- Upload of gzip files does not happen if it is batched with non-gzip files [\#336](https://github.com/NASA-PDS/data-upload-manager/issues/336) [[s.medium](https://github.com/NASA-PDS/data-upload-manager/labels/s.medium)]

**Other closed issues:**

- Incorporate WAF configuration with API Gateway Terraform module [\#252](https://github.com/NASA-PDS/data-upload-manager/issues/252)

## [v2.3.0](https://github.com/NASA-PDS/data-upload-manager/tree/v2.3.0) (2026-01-29)

[Full Changelog](https://github.com/NASA-PDS/data-upload-manager/compare/v2.2.3...v2.3.0)

**Requirements:**

- As a Node Operator, I want weblogs to be validated as gzipped prior to upload [\#330](https://github.com/NASA-PDS/data-upload-manager/issues/330)
- As a user, I can read rclone-generated checksums when checking for existing files in the staging bucket [\#209](https://github.com/NASA-PDS/data-upload-manager/issues/209)
- As a user, I want to force an upload of file that is already in the archive bucket [\#100](https://github.com/NASA-PDS/data-upload-manager/issues/100)
- As a user, I want to skip upload of files that are already in the archive bucket [\#99](https://github.com/NASA-PDS/data-upload-manager/issues/99)

**Defects:**

- S3 operations do not validate bucket ownership leading to Confused Deputy vulnerability [\#321](https://github.com/NASA-PDS/data-upload-manager/issues/321) [[s.high](https://github.com/NASA-PDS/data-upload-manager/labels/s.high)]
- S3 client initialization does not use explicit IAM role credentials [\#318](https://github.com/NASA-PDS/data-upload-manager/issues/318) [[s.medium](https://github.com/NASA-PDS/data-upload-manager/labels/s.medium)]
- Summary table bytes transferred does not calculate correctly with multiple threads [\#304](https://github.com/NASA-PDS/data-upload-manager/issues/304) [[s.medium](https://github.com/NASA-PDS/data-upload-manager/labels/s.medium)]

**Other closed issues:**

- B13.1 Deliver Manager [\#331](https://github.com/NASA-PDS/data-upload-manager/issues/331)
- Update terraform to include required tags [\#328](https://github.com/NASA-PDS/data-upload-manager/issues/328)
- Run and Test DUM for Uploading Web Logs [\#294](https://github.com/NASA-PDS/data-upload-manager/issues/294)

## [v2.2.3](https://github.com/NASA-PDS/data-upload-manager/tree/v2.2.3) (2025-10-22)

[Full Changelog](https://github.com/NASA-PDS/data-upload-manager/compare/v2.2.2...v2.2.3)

## [v2.2.2](https://github.com/NASA-PDS/data-upload-manager/tree/v2.2.2) (2025-10-06)

[Full Changelog](https://github.com/NASA-PDS/data-upload-manager/compare/v2.2.1...v2.2.2)

**Improvements:**

- Enable Python 3.12 compatibility [\#289](https://github.com/NASA-PDS/data-upload-manager/issues/289)

## [v2.2.1](https://github.com/NASA-PDS/data-upload-manager/tree/v2.2.1) (2025-10-02)

[Full Changelog](https://github.com/NASA-PDS/data-upload-manager/compare/v2.2.0...v2.2.1)

## [v2.2.0](https://github.com/NASA-PDS/data-upload-manager/tree/v2.2.0) (2025-09-29)

[Full Changelog](https://github.com/NASA-PDS/data-upload-manager/compare/v2.1.2...v2.2.0)

**Requirements:**

- As a user, I want to specify in include/exclude filters for the set of input file paths [\#262](https://github.com/NASA-PDS/data-upload-manager/issues/262)
- As a user, I want to load web logs to the web analytics bucket [\#232](https://github.com/NASA-PDS/data-upload-manager/issues/232)
- As a user, I want to support upload of files \>5GB [\#221](https://github.com/NASA-PDS/data-upload-manager/issues/221)
- As a user, I want to upload files to S3 Glacier directly via DUM [\#205](https://github.com/NASA-PDS/data-upload-manager/issues/205)
- As a user, I want timestamps to the ongoing logs that are printed to stdout while running the job [\#118](https://github.com/NASA-PDS/data-upload-manager/issues/118)
- As a user, I want to resume/rerun upload on a directory and only have the updates or missing files uploaded [\#34](https://github.com/NASA-PDS/data-upload-manager/issues/34)

**Improvements:**

- Develop Ingress Lambda Logging Conventions [\#6](https://github.com/NASA-PDS/data-upload-manager/issues/6)

**Defects:**

- During DUM load, undocumented message about "Backing off" [\#282](https://github.com/NASA-PDS/data-upload-manager/issues/282) [[s.medium](https://github.com/NASA-PDS/data-upload-manager/labels/s.medium)]
- DUM output has typo [\#271](https://github.com/NASA-PDS/data-upload-manager/issues/271) [[s.low](https://github.com/NASA-PDS/data-upload-manager/labels/s.low)]
- When DUM crashes, the report it generates falsely indicates success [\#241](https://github.com/NASA-PDS/data-upload-manager/issues/241) [[s.medium](https://github.com/NASA-PDS/data-upload-manager/labels/s.medium)]

**Other closed issues:**

- Incorporate simulated failure mechanism into the DUM client [\#254](https://github.com/NASA-PDS/data-upload-manager/issues/254)
- Improve error reporting when encountering 403 errors [\#253](https://github.com/NASA-PDS/data-upload-manager/issues/253)
- Add HTTP 104 Error to Backoff/Retry Logic [\#222](https://github.com/NASA-PDS/data-upload-manager/issues/222)
- DUM set up with IMG node [\#211](https://github.com/NASA-PDS/data-upload-manager/issues/211)
- Develop prototype Ingress Status utility [\#203](https://github.com/NASA-PDS/data-upload-manager/issues/203)
- Include cognito link for password update in the email [\#194](https://github.com/NASA-PDS/data-upload-manager/issues/194)
- Investigate monitoring solutions for very long running jobs [\#182](https://github.com/NASA-PDS/data-upload-manager/issues/182)
- Update S3 terraform to use pds-mcp-infra modules [\#180](https://github.com/NASA-PDS/data-upload-manager/issues/180)
- The bucket-map.yaml file used for terraform deployments should be pulled from a private location   [\#82](https://github.com/NASA-PDS/data-upload-manager/issues/82)
- Update installation documentation to only use virtual environment only [\#76](https://github.com/NASA-PDS/data-upload-manager/issues/76)

## [v2.1.2](https://github.com/NASA-PDS/data-upload-manager/tree/v2.1.2) (2025-02-26)

[Full Changelog](https://github.com/NASA-PDS/data-upload-manager/compare/v2.1.1...v2.1.2)

## [v2.1.1](https://github.com/NASA-PDS/data-upload-manager/tree/v2.1.1) (2025-02-26)

[Full Changelog](https://github.com/NASA-PDS/data-upload-manager/compare/v2.0.0...v2.1.1)

**Requirements:**

- As a user, I want to provide a checksum manifest as input to verify the checksums being generated by data upload manager [\#122](https://github.com/NASA-PDS/data-upload-manager/issues/122)

**Other closed issues:**

- Use the s3 terraform module in mcp-pds-infra [\#181](https://github.com/NASA-PDS/data-upload-manager/issues/181)
- Deploy v2.0.0 DUM to Production [\#161](https://github.com/NASA-PDS/data-upload-manager/issues/161)
- Investigate usage of localstack for use with DUM local integration testing [\#134](https://github.com/NASA-PDS/data-upload-manager/issues/134)

## [v2.0.0](https://github.com/NASA-PDS/data-upload-manager/tree/v2.0.0) (2024-08-29)

[Full Changelog](https://github.com/NASA-PDS/data-upload-manager/compare/v1.2.0...v2.0.0)

**Requirements:**

- As a user, I want to include the modification datetime in the the user-defined object metadata being sent in the upload payload [\#87](https://github.com/NASA-PDS/data-upload-manager/issues/87)
- As a user, I want to include a MD5 checksum in the the user-defined object metadata being sent in the upload payload [\#50](https://github.com/NASA-PDS/data-upload-manager/issues/50)
- Add argument to client script to follow symlinks [\#44](https://github.com/NASA-PDS/data-upload-manager/issues/44)

**Defects:**

- Backoff/Retry logic not firing for certain error codes [\#136](https://github.com/NASA-PDS/data-upload-manager/issues/136) [[s.medium](https://github.com/NASA-PDS/data-upload-manager/labels/s.medium)]
- DUM Client script does not respect configured logging level after a transfer failure/retry [\#135](https://github.com/NASA-PDS/data-upload-manager/issues/135) [[s.medium](https://github.com/NASA-PDS/data-upload-manager/labels/s.medium)]
- DUM Lambda Service can return pre-signed S3 URL's to non-existing buckets [\#116](https://github.com/NASA-PDS/data-upload-manager/issues/116) [[s.high](https://github.com/NASA-PDS/data-upload-manager/labels/s.high)]
- Backoff/Retry logic masks errors from urllib3 exceptions [\#115](https://github.com/NASA-PDS/data-upload-manager/issues/115) [[s.medium](https://github.com/NASA-PDS/data-upload-manager/labels/s.medium)]
- DUM Client does not properly sanitize double-quotes from INI config [\#110](https://github.com/NASA-PDS/data-upload-manager/issues/110) [[s.high](https://github.com/NASA-PDS/data-upload-manager/labels/s.high)]

**Other closed issues:**

- Deploy v1.2.0 DUM to Production [\#108](https://github.com/NASA-PDS/data-upload-manager/issues/108)
- Upgrade SBN to latest and Rename Bucket Folder [\#97](https://github.com/NASA-PDS/data-upload-manager/issues/97)

## [v1.2.0](https://github.com/NASA-PDS/data-upload-manager/tree/v1.2.0) (2024-05-14)

[Full Changelog](https://github.com/NASA-PDS/data-upload-manager/compare/v1.1.0...v1.2.0)

**Requirements:**

- As a user, I want an end summary report in logs to show statistics of files uploaded [\#98](https://github.com/NASA-PDS/data-upload-manager/issues/98)

**Other closed issues:**

- Implement automatic refresh of Cognito authentication token [\#104](https://github.com/NASA-PDS/data-upload-manager/issues/104)

## [v1.1.0](https://github.com/NASA-PDS/data-upload-manager/tree/v1.1.0) (2024-04-25)

[Full Changelog](https://github.com/NASA-PDS/data-upload-manager/compare/v1.0.0...v1.1.0)

**Requirements:**

- As a user, I want to skip upload of files already in S3 \(nucleus staging bucket\) [\#92](https://github.com/NASA-PDS/data-upload-manager/issues/92)
- As a user, I want to upload only data products that have not been previously ingested [\#33](https://github.com/NASA-PDS/data-upload-manager/issues/33)

**Defects:**

- DUM client is unable to create CloudWatch Log Stream pds-ingress-client-sbn-\* when upload data to cloud [\#75](https://github.com/NASA-PDS/data-upload-manager/issues/75) [[s.medium](https://github.com/NASA-PDS/data-upload-manager/labels/s.medium)]

**Other closed issues:**

- Update lambda function to lowercase the node prefix in buckets [\#90](https://github.com/NASA-PDS/data-upload-manager/issues/90)

## [v1.0.0](https://github.com/NASA-PDS/data-upload-manager/tree/v1.0.0) (2024-03-07)

[Full Changelog](https://github.com/NASA-PDS/data-upload-manager/compare/v0.3.0...v1.0.0)

**Other closed issues:**

- Temporarily disable centralized logging [\#78](https://github.com/NASA-PDS/data-upload-manager/issues/78)
- Test upload subset of CSS with manual trigger of Nucleus [\#32](https://github.com/NASA-PDS/data-upload-manager/issues/32)

## [v0.3.0](https://github.com/NASA-PDS/data-upload-manager/tree/v0.3.0) (2023-11-06)

[Full Changelog](https://github.com/NASA-PDS/data-upload-manager/compare/v0.2.0...v0.3.0)

**Defects:**

- Log upload to Cloudwatch fails during batch upload [\#43](https://github.com/NASA-PDS/data-upload-manager/issues/43) [[s.high](https://github.com/NASA-PDS/data-upload-manager/labels/s.high)]

**Other closed issues:**

- Populate Sphinx documentation for entire DUM service [\#47](https://github.com/NASA-PDS/data-upload-manager/issues/47)
- Upload test data set with manual trigger of Nucleus [\#31](https://github.com/NASA-PDS/data-upload-manager/issues/31)

## [v0.2.0](https://github.com/NASA-PDS/data-upload-manager/tree/v0.2.0) (2023-10-17)

[Full Changelog](https://github.com/NASA-PDS/data-upload-manager/compare/v0.1.0...v0.2.0)

**Requirements:**

- As a user, I want to parallelize upload of data products to PDC [\#24](https://github.com/NASA-PDS/data-upload-manager/issues/24)
- Develop Ingress Client Logging Capabilities [\#21](https://github.com/NASA-PDS/data-upload-manager/issues/21)
- As a user, I want to use Cognito Single Sign On to authenticate to the DUM service [\#10](https://github.com/NASA-PDS/data-upload-manager/issues/10)

**Improvements:**

- Add support for presigned upload URL usage [\#26](https://github.com/NASA-PDS/data-upload-manager/issues/26)

**Other closed issues:**

- Develop initial design doc [\#3](https://github.com/NASA-PDS/data-upload-manager/issues/3)

## [v0.1.0](https://github.com/NASA-PDS/data-upload-manager/tree/v0.1.0) (2023-05-16)

[Full Changelog](https://github.com/NASA-PDS/data-upload-manager/compare/ed1ba8db788146a62149df3915d6ccc0c4bcf6c6...v0.1.0)

**Other closed issues:**

- verify the node of the user against Cognito [\#18](https://github.com/NASA-PDS/data-upload-manager/issues/18)
- Investigate integration of authentication Lambda/Cognito with API Gateway [\#16](https://github.com/NASA-PDS/data-upload-manager/issues/16)
- Develop Ingress Client Interface [\#8](https://github.com/NASA-PDS/data-upload-manager/issues/8)
- Add External Config Support to Ingress Client Script [\#7](https://github.com/NASA-PDS/data-upload-manager/issues/7)
- Develop Ingress Service Routing Logic [\#5](https://github.com/NASA-PDS/data-upload-manager/issues/5)
- Develop Initial Proof-of-Concept [\#2](https://github.com/NASA-PDS/data-upload-manager/issues/2)
- Develop Initial Design and Architecture [\#1](https://github.com/NASA-PDS/data-upload-manager/issues/1)



\* *This Changelog was automatically generated by [github_changelog_generator](https://github.com/github-changelog-generator/github-changelog-generator)*
