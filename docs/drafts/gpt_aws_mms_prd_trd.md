# Product Requirements Document (PRD)
## Automatic Weather Station Maintenance Management System

**Document Version:** 1.0  
**Date:** 2026-10-15  
**Status:** MVP Definition

---

## 1. Product Overview

The Automatic Weather Station Maintenance Management System (AWS-MMS) is a web-based maintenance-management application for an organization that operates and maintains Automatic Weather Stations (AWS) for multiple external client organizations.

The system will provide a central platform for:

- Managing clients and their AWS assets
- Allowing clients to submit and track maintenance requests
- Managing approval, assignment, scheduling, and completion of maintenance requests
- Recording one or more site visits against a maintenance request
- Capturing before, during, and after site-visit media
- Recording maintenance work and component changes
- Managing station configurations and technical documentation
- Generating standardized maintenance and site-visit reports
- Allowing clients to review and confirm completed maintenance
- Maintaining an immutable audit trail
- Providing station QR-code access
- Supporting offline-capable field workflows
- Providing secure APIs for future integration with telemetry, MQTT, and weather-dashboard systems

The initial release is a **reactive maintenance-management system**. Preventive-maintenance schedules will be supported as informational records but will not automatically generate maintenance requests.

---

## 2. Goals

### 2.1 Primary Goals

1. Provide clients with a simple mechanism to submit AWS maintenance requests.
2. Give clients visibility into the status and history of their requests.
3. Give maintenance staff a structured workflow for executing and documenting field work.
4. Create a complete digital maintenance history for every AWS.
5. Centralize station configurations and technical documentation.
6. Generate consistent, professional reports from structured maintenance data.
7. Maintain strong role-based and client-based data isolation.
8. Support field work where internet connectivity may be unreliable.
9. Provide an extensible API architecture for future integrations.

### 2.2 Secondary Goals

- Reduce manual report preparation.
- Improve traceability of configuration changes.
- Improve communication between clients and maintenance staff.
- Provide historical evidence of work performed.
- Establish a foundation for future asset management and preventive maintenance.

---

## 3. Non-Goals for MVP

The MVP will not:

- Act as an AWS telemetry ingestion platform.
- Store or process continuous weather observations.
- Automatically generate maintenance requests from telemetry failures.
- Provide full inventory/procurement management.
- Require GPS tracking of technicians.
- Require MFA/2FA.
- Automatically generate preventive-maintenance requests.
- Provide public, unauthenticated station dashboards.

Telemetry and weather-dashboard integrations will be supported through future APIs/integration services.

---

## 4. Users and Roles

The application supports staff belonging to the operating organization and external client users.

### 4.1 System Admin

Full system-administration privileges.

Capabilities:

- Manage clients
- Manage users
- Assign roles
- Manage stations
- Manage station components
- Approve/deny maintenance requests
- Assign technicians
- Schedule maintenance visits
- View and modify maintenance records where authorized
- Manage station documentation
- Manage configuration records
- View reports
- View audit logs
- Manage system configuration

### 4.2 Maintenance Technician

Field-maintenance role.

Capabilities:

- View all stations
- View maintenance requests
- Claim available requests
- Accept assignments
- Participate in site visits
- Start/complete site visits
- Record maintenance work
- Record component replacements
- Upload images and videos
- Upload configuration files
- Add report details
- Generate/finalize site-visit reports

### 4.3 Viewer

Read-only internal role.

Capabilities:

- View stations
- View station components
- View maintenance requests
- View site visits
- View maintenance history
- View documentation
- View configurations
- View reports

No modification privileges.

### 4.4 Client User

External user associated with one client organization.

Capabilities:

- View only their organization's AWS stations
- Submit maintenance requests
- View maintenance-request status
- Comment on requests
- Upload client reports
- Review completed maintenance
- Accept or reject completed maintenance
- Provide rejection reasons
- View station documentation and reports where permitted

---

## 5. Organization and Data Isolation

The system initially serves one operating organization with multiple external clients.

Each client may own multiple AWSs.

Relationship:

```text
Operating Organization
├── Staff
│   ├── System Admin
│   ├── Maintenance Technician
│   └── Viewer
│
└── Clients
    ├── Client A
    │   ├── User(s)
    │   └── AWSs
    ├── Client B
    │   ├── User(s)
    │   └── AWSs
    └── Client C
        ├── User(s)
        └── AWSs
```

A station belongs to exactly one client.

Client users may access only stations owned by their client.

Staff may access all stations.

Authorization must be enforced server-side and must not depend solely on frontend filtering.

---

## 6. Core Concepts

### 6.1 Station

An AWS is the primary managed asset.

A station contains:

- Station ID
- Station name
- Station type
- Owner/client
- Country
- Latitude
- Longitude
- Elevation
- Parameters
- Components/sensors
- Configuration history
- Documentation
- Maintenance history
- QR code

Example parameters:

- AT
- RH
- BP
- RAIN
- Wind Speed
- Wind Direction
- Solar Radiation
- Other configured parameters

### 6.2 Maintenance Request

A maintenance request represents a client-reported or staff-created maintenance requirement.

A request can contain one or more site visits.

### 6.3 Site Visit

A site visit represents a physical journey to a station to investigate, repair, inspect, configure, or otherwise perform maintenance.

Multiple site visits may belong to one maintenance request.

### 6.4 Component

A component represents a physical station subsystem or sensor.

Examples:

- Temperature/RH sensor
- Barometer
- Rain gauge
- Anemometer
- Wind vane
- Data logger
- Modem
- Battery
- Solar panel

### 6.5 Configuration

A configuration is a versioned collection of station configuration files.

### 6.6 Document

A technical document associated with a station.

Examples:

- Datasheet
- Operational manual
- Maintenance manual
- Calibration certificate
- Installation document

---

## 7. Functional Requirements

## 7.1 Authentication

The system shall provide:

- User registration
- Login
- Logout
- Password reset
- Password change
- Access-token management
- Refresh-token management
- Role-based authorization
- Client-level data authorization

MFA is not required for MVP.

---

## 7.2 Client Management

System Admin shall be able to:

- Create clients
- Edit client information
- Activate/deactivate clients
- Create/manage client users
- Associate users with clients
- View client-owned stations

---

## 7.3 Station Management

Authorized staff shall be able to:

- Create stations
- Edit station metadata
- Assign a station to a client
- Define station type
- Define station parameters
- Store geographic information
- Manage station components
- View station maintenance history
- View station documents
- View configuration history
- Generate station QR codes

A station shall belong to exactly one client.

---

## 7.4 Station QR Codes

Each station shall have a unique QR code.

Scanning the QR code shall:

1. Open the application.
2. Identify the station.
3. Require authentication.
4. Verify user authorization.
5. Display the station information available to that user.

A technician shall be able to start a site visit directly from the station page.

The QR code shall use an opaque/public station identifier and shall not contain sensitive station information.

---

## 7.5 Maintenance Requests

Clients shall be able to create maintenance requests.

A request shall include:

- Request number
- Station
- Title
- Description
- Category
- Priority
- Attachments
- Submitted by
- Submission date/time
- Current status

Requests shall support comments and ongoing communication.

---

## 7.6 Maintenance Request Workflow

The request lifecycle shall support:

```text
Draft
  ↓
Pending Approval
  ↓
Approved / Denied
  ↓
Assigned
  ↓
Scheduled
  ↓
Active
  ↓
Technician Completed
  ↓
Client Review
  ↓
Accepted → Closed
Rejected → Reopened → Active
```

A maintenance request may contain multiple site visits.

System Admin or Maintenance Technician may claim an available request.

Multiple technicians may be assigned to one request.

Multiple technicians may participate in one site visit.

---

## 7.7 Request Approval

System Admin shall be able to:

- Approve requests
- Deny requests
- Provide approval/denial comments
- View approval history

A denied request shall record:

- Approver
- Timestamp
- Reason

---

## 7.8 Scheduling

Authorized staff shall be able to schedule site visits.

Scheduling shall support:

- Technician assignment
- Multiple technicians
- Date
- Planned start time
- Planned end time
- Visit notes
- Rescheduling
- Cancellation

The MVP shall provide basic scheduling rather than a complex workforce-management system.

---

## 7.9 Site Visit

A site visit shall support:

### Before visit

- Start visit
- Record actual start time
- Upload images
- Upload videos
- Record initial station condition

### During visit

- Record work performed
- Add technician notes
- Record tests
- Record component replacements
- Record configuration changes
- Upload media

### After visit

- Record final station condition
- Upload images
- Upload videos
- Record actual completion/departure time
- Complete the site visit
- Generate/update report

GPS capture is not required.

---

## 7.10 Offline Field Operation

The technician field workflow shall support offline operation.

When offline, the application shall be able to retain locally:

- Site-visit state
- Text entries
- Maintenance records
- Media metadata
- Images
- Videos
- Configuration files where practical

The application shall maintain a synchronization queue.

When connectivity returns, queued records shall synchronize with the backend.

The system shall avoid duplicate records during synchronization.

---

## 7.11 Maintenance Work Recording

Technicians shall be able to record both structured and free-text information.

Structured information may include:

- Work performed
- Tests performed
- Component replaced
- Component installed
- Component serial number
- Reason for replacement
- Configuration change
- Calibration information
- Additional notes

The system shall support custom maintenance details without requiring every type of maintenance activity to be predefined.

---

## 7.12 Station Components

Each station shall support a component inventory.

Each component may contain:

- Component type
- Parameter
- Manufacturer
- Model
- Serial number
- Installation date
- Calibration date
- Calibration due date
- Status
- Notes
- Documentation

The system shall retain component history.

---

## 7.13 Configuration Management

The application shall support station configuration files including:

- TXT
- XML
- JSON
- Python
- Network configuration
- Modem configuration
- Related photos

Configurations shall be versioned.

Every configuration version shall include:

- Version identifier
- Upload timestamp
- Uploaded by
- Files
- Description/change notes
- Relationship to the relevant station/site visit

Existing configurations shall not be overwritten.

---

## 7.14 Station Documentation

Station documentation shall support:

- Datasheets
- Operational manuals
- Maintenance manuals
- Calibration certificates
- Installation documents
- Other technical documents

Documents shall be associated with stations.

Document metadata shall include:

- Filename
- Document type
- Version
- Description
- Uploaded by
- Upload timestamp
- Storage location

---

## 7.15 Media Management

The application shall support:

- Images
- Videos

Media shall be categorized as:

- Before visit
- During visit
- After visit

The system shall support:

- Image compression
- WebP conversion
- Thumbnail generation
- Video transcoding
- Video thumbnail generation

Pillow shall be used for image processing.

FFmpeg shall be used for video processing.

Original media should be retained where storage capacity permits.

Local object storage shall be used rather than storing media binary data directly in MongoDB.

---

## 7.16 Client Confirmation

After technicians complete the maintenance work, the request shall enter Client Review.

The client shall be able to:

- Review the work
- Review site-visit details
- Review media
- Review reports
- Add comments
- Accept completion
- Reject completion

A rejection shall require a reason.

If the client does not respond within 30 days, the system shall automatically close the request.

The automatic closure must be recorded in the audit trail.

---

## 7.17 Client Reports

Clients shall have two reporting options:

1. Complete an online report.
2. Upload their own PDF report.

The client chooses the preferred method.

Online client reports shall be stored as structured data and may be rendered into PDF.

Uploaded client PDFs shall be stored as documents associated with the maintenance request.

---

## 7.18 Reports

The system shall generate standardized reports.

Required report types:

- Maintenance Request Report
- Site Visit Report
- Station Maintenance History Report
- Station Asset Report
- Configuration Report
- Monthly Maintenance Report
- Annual Maintenance Report
- Client-specific Reports
- Staff Workload Reports
- Maintenance Statistics Reports

Technicians shall be able to add or modify relevant report details before finalization.

Reports shall support:

- Organization information
- Client information
- Station information
- Request information
- Site visits
- Technicians
- Work performed
- Components
- Configuration changes
- Before/during/after media
- Comments
- Client response
- Signatures
- Dates/times

---

## 7.19 Electronic Signatures

The system shall support electronic signatures for:

- Technician
- Client

The system shall record:

- Signer
- Timestamp
- Role
- Associated report/version

---

## 7.20 Notifications

The application shall generate notifications for important workflow events.

Examples:

- Maintenance request submitted
- Request approved
- Request denied
- Technician assigned
- Site visit scheduled
- Site visit rescheduled
- Site visit completed
- Maintenance completed
- Client review required
- Client rejected completion
- Request closed
- Request automatically closed

MVP notification channels:

- In-app
- Email

SMS/push may be added later.

---

## 7.21 Preventive Maintenance

The system shall support preventive-maintenance plans.

A plan shall contain:

- Station
- Component
- Maintenance type
- Frequency
- Last performed
- Next due date
- Instructions
- Notes

The system shall display upcoming/overdue preventive maintenance.

The MVP shall not automatically generate maintenance requests from preventive-maintenance plans.

---

## 7.22 Audit Trail

The system shall maintain an immutable audit trail.

Audited actions shall include:

- Login/security events
- User changes
- Station changes
- Request creation
- Approval/denial
- Assignment
- Scheduling
- Site-visit state changes
- Media uploads
- Configuration uploads
- Document uploads
- Report finalization
- Client acceptance/rejection
- Automatic closure

Audit records shall contain:

- Actor
- Role
- Action
- Resource type
- Resource ID
- Timestamp
- Relevant before/after values
- Metadata

Normal application users shall not be able to modify audit events.

---

## 8. User Experience Requirements

The interface shall be responsive and desktop/tablet/mobile friendly.

### Client Dashboard

Should show:

- Client stations
- Open maintenance requests
- Requests awaiting review
- Recently completed requests
- Upcoming scheduled visits
- Notifications

### Technician Dashboard

Should show:

- Assigned requests
- Available requests
- Scheduled visits
- Active visits
- Overdue work
- Recently completed visits

### Admin Dashboard

Should show:

- Pending approvals
- Active requests
- Scheduled visits
- Overdue requests
- Requests awaiting client confirmation
- Recently completed work
- Client/station statistics

---

## 9. Search and Filtering

The system shall support searching/filtering by:

- Station
- Client
- Station type
- Request status
- Priority
- Request category
- Technician
- Date range
- Site visit status
- Component
- Report status

---

## 10. API Requirements

The application shall expose secure APIs for:

- Authentication
- Users
- Clients
- Stations
- Components
- Maintenance requests
- Site visits
- Media
- Documents
- Configurations
- Reports
- Notifications
- Audit events
- Integrations

External API access shall use secure token/API-key authentication.

---

## 11. Future Integration Requirements

The architecture shall support integration with:

- AWS telemetry platform
- MQTT
- MongoDB-based systems
- Weather dashboards
- External APIs

The maintenance system shall remain logically separate from continuous AWS telemetry ingestion.

---

## 12. MVP Acceptance Criteria

The MVP is successful when:

1. A client can log in and see only their stations.
2. A client can submit a maintenance request.
3. An admin can approve or deny the request.
4. A technician can claim or be assigned the request.
5. A site visit can be scheduled and performed.
6. A technician can record work performed.
7. Technicians can upload before/during/after images and videos.
8. Media can be processed and stored in object storage.
9. A technician can upload configuration files.
10. Configuration versions are timestamped and retained.
11. Station documentation can be stored and retrieved.
12. Multiple site visits can exist under one request.
13. A report can be generated from maintenance data.
14. Technicians can edit report details before finalization.
15. A client can review completed maintenance.
16. A client can accept or reject completion.
17. Rejection requires a reason.
18. Requests can automatically close after 30 days without client response.
19. Users cannot access data outside their authorization scope.
20. Significant actions are recorded in an immutable audit trail.
21. A station QR code can open the authenticated station page.
22. A technician can initiate a site visit from the station page.
23. Field data can be captured offline and synchronized later.
24. The system can run using Docker Compose.

---

# 13. Technical Requirements Document (TRD)

## 13.1 Technical Architecture

The system shall use a modular microservices architecture built around:

- Vue 3
- TypeScript
- FastAPI
- Python
- MongoDB
- Kong
- Redis
- RabbitMQ
- MinIO
- Docker Compose

The frontend communicates only with the API Gateway.

```text
Vue PWA
   ↓ HTTPS
Kong API Gateway
   ↓
FastAPI Services
   ↓
MongoDB / MinIO / RabbitMQ / Redis
```

---

## 13.2 Service Boundaries

### Auth Service

Responsibilities:

- Authentication
- User lifecycle
- Password management
- JWT issuance
- Refresh tokens
- RBAC
- Client association

Primary collections:

```text
users
roles
sessions
password_reset_tokens
```

---

### Station Service

Responsibilities:

- Clients
- Stations
- Components
- Station parameters
- QR codes
- Station metadata

Collections:

```text
clients
stations
station_components
station_qr
```

---

### Maintenance Service

Responsibilities:

- Maintenance requests
- Request workflow
- Approval
- Assignment
- Scheduling metadata
- Client confirmation
- Comments
- Preventive-maintenance plans

Collections:

```text
maintenance_requests
maintenance_comments
maintenance_plans
```

---

### Visit Service

Responsibilities:

- Site visits
- Technician participation
- Visit lifecycle
- Maintenance activities
- Tests
- Component replacement records
- Visit notes

Collections:

```text
site_visits
maintenance_activities
component_changes
```

---

### Media Service

Responsibilities:

- Uploads
- Media metadata
- Image processing
- Video processing
- Thumbnails
- Object-storage integration

Collection:

```text
media
```

---

### Document Service

Responsibilities:

- Station documents
- Configuration files
- Configuration versions
- File metadata
- Document access

Collections:

```text
documents
configurations
configuration_versions
```

---

### Report Service

Responsibilities:

- Report templates
- Report data aggregation
- PDF generation
- Report versions
- Electronic signatures

Collections:

```text
reports
report_versions
signatures
```

---

## 13.3 Supporting Workers

### Notification Worker

Consumes events and sends:

- Email
- In-app notifications

### Audit Worker

Consumes application events and creates immutable audit records.

Collection:

```text
audit_events
```

### Integration Service

Provides secure integration endpoints for:

- Telemetry platform
- MQTT-related integrations
- Weather dashboards
- External API consumers

---

## 14. Database Architecture

The initial deployment shall use one MongoDB cluster.

Logical ownership shall remain separated by service.

Recommended initial database:

```text
aws_mms
```

Collections may include:

```text
users
roles
clients
stations
station_components

maintenance_requests
maintenance_comments
maintenance_plans

site_visits
maintenance_activities
component_changes

media
documents
configurations
configuration_versions

reports
report_versions
signatures

notifications
audit_events

integration_tokens
```

Services must not freely modify another service's collections.

---

## 15. Core Data Relationships

```text
Client
  │
  └── 1:N ── Station
                 │
                 ├── 1:N ── Component
                 ├── 1:N ── Document
                 ├── 1:N ── ConfigurationVersion
                 └── 1:N ── MaintenanceRequest
                                      │
                                      ├── 1:N ── SiteVisit
                                      │                │
                                      │                └── 1:N ── Media
                                      │
                                      ├── 1:N ── Comment
                                      │
                                      ├── 1:N ── ClientReport
                                      │
                                      └── 1:N ── Report
```

---

## 16. Example Station Document

```json
{
  "_id": "station_001",
  "stationCode": "AWS-001",
  "name": "AWS Main Station",
  "type": "automatic_weather_station",
  "clientId": "client_001",
  "location": {
    "latitude": 13.1234,
    "longitude": -59.5678,
    "elevationM": 120
  },
  "parameters": [
    "AT",
    "RH",
    "BP",
    "RAIN",
    "WS",
    "WD"
  ],
  "status": "active",
  "qrCodeId": "qr_xxxxx",
  "createdAt": "2026-10-15T00:00:00Z",
  "updatedAt": "2026-10-15T00:00:00Z"
}
```

---

## 17. Example Maintenance Request

```json
{
  "_id": "req_001",
  "requestNumber": "MR-2026-00124",
  "clientId": "client_001",
  "stationId": "station_001",
  "title": "Station stopped transmitting",
  "description": "AWS has not transmitted observations since yesterday.",
  "priority": "high",
  "category": "communications",
  "status": "pending_approval",
  "submittedBy": "user_001",
  "submittedAt": "2026-10-15T12:00:00Z",
  "technicians": [],
  "createdAt": "2026-10-15T12:00:00Z",
  "updatedAt": "2026-10-15T12:00:00Z"
}
```

---

## 18. Site Visit Data

```json
{
  "_id": "visit_001",
  "maintenanceRequestId": "req_001",
  "stationId": "station_001",
  "technicians": [
    "user_tech_001"
  ],
  "status": "completed",
  "plannedStart": "2026-10-20T09:00:00Z",
  "plannedEnd": "2026-10-20T15:00:00Z",
  "actualStart": "2026-10-20T09:12:00Z",
  "actualEnd": "2026-10-20T14:48:00Z",
  "initialCondition": "...",
  "maintenancePerformed": "...",
  "finalCondition": "...",
  "configurationChanges": [],
  "mediaIds": [],
  "reportId": "report_001"
}
```

---

## 19. Configuration Versioning

Configuration records shall use immutable versions.

```text
Configuration
    │
    ├── Version 1
    ├── Version 2
    ├── Version 3
    └── Version 4 ← current
```

A version should contain:

```json
{
  "_id": "config_version_004",
  "stationId": "station_001",
  "version": 4,
  "files": [
    {
      "filename": "station.json",
      "storageKey": "..."
    },
    {
      "filename": "modem.txt",
      "storageKey": "..."
    }
  ],
  "changeDescription": "Updated modem configuration.",
  "uploadedBy": "user_tech_001",
  "uploadedAt": "2026-10-15T14:00:00Z"
}
```

Versions must not be deleted or overwritten through normal application operations.

---

## 20. Object Storage

MinIO shall be used for local object storage.

Suggested buckets:

```text
aws-mms-media
aws-mms-documents
aws-mms-configurations
aws-mms-reports
```

Object keys should be generated by the backend.

Example:

```text
media/
  client/{clientId}/
  station/{stationId}/
  visit/{visitId}/
  before/{mediaId}.webp
```

---

## 21. Media Pipeline

### Image

```text
Upload
  ↓
Validation
  ↓
Object Storage
  ↓
Pillow Worker
  ├── Resize
  ├── Compress
  ├── WebP conversion
  └── Thumbnail
```

### Video

```text
Upload
  ↓
Validation
  ↓
Object Storage
  ↓
FFmpeg Worker
  ├── Transcode
  └── Generate thumbnail
```

Media processing should be asynchronous for large files.

---

## 22. API Gateway

Kong shall be the external API gateway.

Responsibilities:

- TLS termination
- Routing
- Authentication integration
- Rate limiting
- API key validation
- Request logging
- CORS
- Service discovery/routing

Example routes:

```text
/api/v1/auth/*
/api/v1/clients/*
/api/v1/stations/*
/api/v1/maintenance/*
/api/v1/visits/*
/api/v1/media/*
/api/v1/documents/*
/api/v1/configurations/*
/api/v1/reports/*
/api/v1/notifications/*
/api/v1/audit/*
/api/v1/integrations/*
```

---

## 23. Authentication and Authorization

JWT shall be used for user sessions.

Token claims should include:

```json
{
  "sub": "user_001",
  "role": "client_user",
  "clientId": "client_001",
  "iat": 0,
  "exp": 0
}
```

Server-side authorization must verify:

```text
Authenticated
      +
Valid Role
      +
Resource Ownership
```

Example:

```text
GET /stations/AWS-001

Client User
     ↓
station.clientId == token.clientId
     ↓
ALLOW
```

Otherwise:

```text
403 Forbidden
```

---

## 24. API Security

External APIs shall support:

- HTTPS
- JWT authentication
- API keys for machine-to-machine integrations
- Token expiration
- Refresh tokens
- Rate limiting
- Request validation
- Input sanitization
- File-type validation
- File-size limits
- Authorization checks
- Audit logging

No API should expose raw internal MongoDB operations.

---

## 25. Internal Service Communication

Use synchronous HTTP/REST for operations that require an immediate response.

Use RabbitMQ events for asynchronous workflows.

Example:

```text
Maintenance Service
       │
       │ MaintenanceCompleted
       ▼
RabbitMQ
   │       │       │
   ▼       ▼       ▼
Audit   Report  Notification
Worker  Worker   Worker
```

This prevents the maintenance request workflow from being tightly coupled to secondary operations.

---

## 26. Event Examples

Recommended events:

```text
USER_CREATED
USER_ROLE_CHANGED

STATION_CREATED
STATION_UPDATED
COMPONENT_UPDATED

MAINTENANCE_REQUEST_CREATED
MAINTENANCE_REQUEST_APPROVED
MAINTENANCE_REQUEST_DENIED
MAINTENANCE_REQUEST_ASSIGNED
MAINTENANCE_REQUEST_SCHEDULED
MAINTENANCE_REQUEST_COMPLETED
MAINTENANCE_REQUEST_REOPENED
MAINTENANCE_REQUEST_CLOSED

SITE_VISIT_STARTED
SITE_VISIT_COMPLETED

MEDIA_UPLOADED
MEDIA_PROCESSED

CONFIGURATION_UPLOADED
DOCUMENT_UPLOADED

REPORT_GENERATED
REPORT_FINALIZED

CLIENT_ACCEPTED
CLIENT_REJECTED
```

---

## 27. Offline Synchronization

The frontend should be implemented as a PWA.

Local storage technologies may include:

- IndexedDB
- Service Worker
- Local application state

Each offline operation should receive a client-generated operation ID.

Example:

```text
operationId:
device-123:operation-987
```

When synchronized, the backend uses idempotency checks to prevent duplicate processing.

Synchronization flow:

```text
Offline
  ↓
Local Transaction
  ↓
Sync Queue
  ↓
Network Available
  ↓
API
  ↓
Server Validation
  ↓
Commit
  ↓
Sync Acknowledgement
```

---

## 28. Report Generation

Report generation should be asynchronous where appropriate.

```text
User requests report
       ↓
Report Service
       ↓
Collect domain data
       ↓
Render template
       ↓
Generate PDF
       ↓
Store PDF in MinIO
       ↓
Create report metadata
       ↓
Notify user
```

Report templates should be versioned.

---

## 29. Report Editing

Report content should be represented as structured data before final PDF generation.

Example:

```text
Report
├── Introduction
├── Station Information
├── Initial Condition
├── Work Performed
├── Components
├── Tests
├── Configuration
├── Final Condition
├── Media
├── Recommendations
└── Signatures
```

Technicians may add/edit information in applicable sections.

Once finalized, the generated report version should become immutable.

If corrections are required, create a new report version.

---

## 30. Audit Architecture

Audit events should be generated from domain events and important synchronous actions.

The audit record should include:

```json
{
  "actorId": "user_001",
  "actorRole": "maintenance_technician",
  "action": "CONFIGURATION_UPLOADED",
  "resourceType": "station",
  "resourceId": "station_001",
  "timestamp": "2026-10-15T14:00:00Z",
  "metadata": {
    "configurationVersion": 4
  }
}
```

Application users must not have update/delete access to audit records.

---

## 31. Notification Architecture

```text
Domain Event
     ↓
RabbitMQ
     ↓
Notification Worker
     ├── In-App Notification
     └── Email
```

Notifications should be persisted so users can see notification history.

---

## 32. Preventive Maintenance Technical Model

Preventive maintenance is represented by a plan:

```text
{
  "stationId": "...",
  "componentId": "...",
  "maintenanceType": "inspection",
  "frequency": {
    "value": 6,
    "unit": "months"
  },
  "lastPerformed": "...",
  "nextDue": "...",
  "active": true
}
```

The system may flag:

```text
DUE
OVERDUE
UPCOMING
```

but shall not create maintenance requests automatically.

---

## 33. Integration Architecture

The Integration Service provides controlled interfaces to external systems.

```text
External System
      │
      ▼
API Gateway
      │
      ▼
Integration Service
      │
      ├── Telemetry API
      ├── MQTT integration
      └── Weather Dashboard API
```

External systems shall not receive direct MongoDB credentials.

---

## 34. API Key Architecture

Machine-to-machine API clients shall use API keys/tokens.

Keys should have:

- Identifier
- Hash
- Owner
- Description
- Created timestamp
- Expiration
- Status
- Scopes

Example scopes:

```text
stations:read
maintenance:read
maintenance:write
reports:read
telemetry:read
```

Raw API keys should not be stored in plaintext.

---

## 35. Docker Compose

Initial deployment shall use Docker Compose.

Core containers:

```text
frontend
kong

auth-service
station-service
maintenance-service
visit-service
media-service
document-service
report-service

notification-worker
audit-worker
integration-service

mongodb
redis
rabbitmq
minio
```

Services should use environment-based configuration.

Secrets should not be committed to source control.

---

## 36. Repository Structure

A monorepo is recommended for MVP development:

```text
aws-mms/
│
├── frontend/
│
├── services/
│   ├── auth/
│   ├── station/
│   ├── maintenance/
│   ├── visit/
│   ├── media/
│   ├── document/
│   ├── report/
│   └── integration/
│
├── workers/
│   ├── notification/
│   └── audit/
│
├── infrastructure/
│   ├── kong/
│   ├── mongodb/
│   ├── rabbitmq/
│   ├── redis/
│   └── minio/
│
├── docker/
│
├── docs/
│
├── scripts/
│
├── docker-compose.yml
└── README.md
```

Each FastAPI service should have an internal structure similar to:

```text
service/
├── app/
│   ├── api/
│   ├── models/
│   ├── schemas/
│   ├── services/
│   ├── repositories/
│   ├── events/
│   ├── security/
│   └── main.py
│
├── tests/
├── Dockerfile
├── requirements.txt
└── README.md
```

---

## 37. Frontend Architecture

Recommended frontend technologies:

- Vue 3
- TypeScript
- Vue Router
- Pinia
- Vuetify
- PrimeVue
- Tailwind CSS
- PWA support
- IndexedDB for offline data

Feature modules:

```text
modules/
├── auth
├── dashboard
├── clients
├── stations
├── maintenance
├── visits
├── media
├── documents
├── configurations
├── reports
├── notifications
└── administration
```

---

## 38. Testing Requirements

### Unit Tests

Required for:

- Business rules
- State transitions
- Authorization
- Validation
- Report calculations
- File processing
- Synchronization logic

### Integration Tests

Required for:

- API → MongoDB
- API → MinIO
- Service → RabbitMQ
- Authentication
- Authorization
- Report generation

### End-to-End Tests

Core scenarios:

1. Client creates request.
2. Admin approves request.
3. Technician claims request.
4. Technician schedules visit.
5. Technician performs visit.
6. Technician uploads media.
7. Technician records maintenance.
8. Technician finalizes report.
9. Client reviews.
10. Client accepts.
11. Request closes.

Also test rejection/reopening and 30-day automatic closure.

---

## 39. Observability

The system should produce structured logs containing:

- Timestamp
- Service
- Request ID
- User ID where applicable
- Endpoint
- Status
- Error information
- Duration

A correlation/request ID should be propagated across service calls and asynchronous events.

Example:

```text
Request
  ↓
Kong
  ↓ request-id: abc123
Maintenance Service
  ↓ request-id: abc123
RabbitMQ
  ↓ request-id: abc123
Report Worker
  ↓
Audit Worker
```

---

## 40. Backup and Recovery

MongoDB data shall be backed up regularly.

Object storage shall also be backed up independently.

Backups should cover:

- MongoDB
- MinIO
- Application configuration
- Important generated reports

Backup restoration should be periodically tested.

---

## 41. Security Principles

The application shall follow:

- Least privilege
- Server-side authorization
- Secure token handling
- HTTPS everywhere outside trusted internal networks
- Password hashing
- Input validation
- File validation
- Object-storage access controls
- Immutable audit logging
- No secrets in source control
- No direct database exposure to external clients

---

## 42. Performance Targets

Initial target:

- Normal API requests: <500 ms under normal load
- Station dashboard: <2 seconds for typical data
- Request creation: <1 second excluding large file uploads
- Media upload: asynchronous processing
- Report generation: asynchronous for large reports

The system should support at least:

- 50–500 stations
- 50–500 users
- Multiple client organizations
- High media volume accumulated over several years

The architecture should permit horizontal scaling of stateless FastAPI services.

---

## 43. Deployment Environments

At minimum:

```text
Development
Testing
Production
```

Each environment should have independent:

- MongoDB configuration
- MinIO storage
- RabbitMQ
- Redis
- API credentials
- Secrets

---

## 44. MVP Development Sequence

### Phase 1 — Foundation

- Repository
- Docker Compose
- MongoDB
- Redis
- RabbitMQ
- MinIO
- Kong
- FastAPI base service
- Vue application
- Authentication

### Phase 2 — Users and Stations

- Users
- Roles
- Clients
- Stations
- Components
- QR codes
- Authorization

### Phase 3 — Maintenance

- Requests
- Approval
- Assignment
- Scheduling
- Comments
- Status workflow

### Phase 4 — Site Visits

- Site visit creation
- Technician workflow
- Before/during/after media
- Maintenance records
- Component changes
- Offline workflow

### Phase 5 — Files

- Documents
- Configurations
- Versioning
- Media processing

### Phase 6 — Reports

- Report templates
- Report editor
- PDF generation
- Report versions
- Electronic signatures
- Client reports

### Phase 7 — Notifications and Audit

- Notification worker
- Email
- In-app notifications
- Immutable audit trail
- Automatic 30-day closure

### Phase 8 — Integration

- Secure API tokens
- Telemetry integration
- MQTT integration
- Weather-dashboard integration

---

## 45. Definition of Done

The MVP is considered complete when:

- All MVP functional requirements are implemented.
- RBAC is enforced server-side.
- Client data isolation is enforced.
- Maintenance state transitions are validated.
- Multiple site visits are supported.
- Offline synchronization works for core field data.
- Media processing works for supported image/video formats.
- Configuration files are versioned and timestamped.
- Station documentation is searchable and accessible.
- Reports can be generated and finalized.
- Electronic signatures work.
- Client acceptance/rejection works.
- 30-day automatic closure works.
- Audit records cannot be modified through application APIs.
- APIs are documented.
- Core workflows have automated tests.
- Docker Compose can deploy the complete MVP.
- Database and object-storage backup procedures are documented.

---

## 46. Architectural Principles

The implementation should follow these principles:

1. **Station-centric architecture** — the AWS is the core managed asset.
2. **Requests are workflows around stations**, not the primary asset.
3. **Site visits are first-class entities.**
4. **Configuration history is immutable.**
5. **Reports are generated from structured data.**
6. **Media belongs in object storage, not MongoDB.**
7. **Authorization is enforced at the API/service layer.**
8. **Client isolation is mandatory.**
9. **Asynchronous work uses events.**
10. **External integrations use secure APIs rather than direct database access.**
11. **Field workflows must tolerate unreliable connectivity.**
12. **Audit history is immutable.**
13. **Services own their data even when sharing one MongoDB cluster.**
14. **The MVP should remain operationally simple enough for Docker Compose.**
15. **The architecture should allow individual services to scale independently later.**

---

## 47. Future Expansion

The architecture should allow future additions without major redesign:

- Inventory/parts management
- Procurement integration
- Calibration management
- Automated telemetry fault detection
- Preventive-maintenance workflows
- Mobile-native applications
- Advanced GIS
- Technician route planning
- Advanced analytics
- SLA tracking
- Client billing
- Service contracts
- Automated maintenance recommendations
- Kubernetes deployment
- Multi-organization SaaS mode
