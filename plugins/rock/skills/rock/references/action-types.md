# Rock RMS Workflow Action Types

Common workflow action components. The catalog (`~/.claude/passion-rock/catalog.json`) has the full list with EntityType IDs for the connected instance.

## Communication

**SendEmail** -- Send an email using Rock's communication system.
- To: email address or Lava expression (e.g., `{{ Workflow | Attribute:'Email' }}`)
- Subject: plain text or Lava
- Body: HTML with Lava
- FromEmail, FromName: sender info
- Can use communication templates

**SendSms** -- Send an SMS message.
- To: phone number or Lava expression
- Message: plain text or Lava
- FromNumber: must be a configured SMS number in Rock

**SendSystemCommunication** -- Send using a pre-defined system communication template.
- SystemCommunicationId: the template to use
- Recipient: person or Lava expression

## Data

**SetAttributeValue** -- Set a workflow attribute value.
- Attribute: which workflow attribute to set
- Value: the value (can be Lava)

**SetPersonAttribute** -- Set an attribute on a Person record.
- Person: which person (Lava expression)
- Attribute: the person attribute key
- Value: the value

**SetEntityProperty** -- Set a property on any Rock entity.
- EntityType, EntityId, PropertyName, PropertyValue

**RunSQL** -- Execute a SQL query.
- SQLQuery: the SQL to run
- Result attribute to store results

**RunLava** -- Execute Lava code and optionally store the result.
- Lava: the Lava template to execute
- Result attribute to store output

## Flow Control

**ActivateActivity** -- Activate another activity in the workflow.
- ActivityType: which activity to activate

**CompleteActivity** -- Mark the current activity as complete.
- Status: optional status message

**SetWorkflowStatus** -- Update the workflow's status text.
- Status: the new status

**PersistWorkflow** -- Save the workflow to the database (required for multi-step workflows).

**Delay** -- Pause execution for a specified time.
- DelayMinutes, DelayHours, DelayDays: how long to wait

**SetWorkflowName** -- Change the workflow's name dynamically.
- Name: new name (can be Lava)

## Forms

**UserEntryForm** -- Display a form for user data entry.
- Configured via WorkflowActionForm and WorkflowActionFormAttribute entities
- The form's attributes reference workflow attributes
- Buttons can activate other activities or complete the workflow

## People

**AddPersonToGroup** -- Add a person to a Rock group.
- Person, GroupId, GroupRoleId

**CreatePerson** -- Create a new Person record.
- FirstName, LastName, Email, etc.
- Returns the new PersonId

**CreateConnectionRequest** -- Create a connection request.
- Person, ConnectionTypeId, ConnectionOpportunityId, Comments

## Integrations

**WebhookSend** -- Send an HTTP request to an external URL.
- Url, Method (GET/POST/PUT), Body, Headers
- Result attribute to store response

**BackgroundCheckRequest** -- Initiate a background check.
- Person, provider settings

## Workflow Management

**LaunchWorkflow** -- Start a new workflow from within a workflow.
- WorkflowTypeId: which workflow to launch
- Can pass attribute values to the new workflow

**DeleteWorkflow** -- Delete the current workflow.

## Notes

- Action types reference EntityType IDs. Use the catalog to get the correct ID for your Rock instance.
- Actions execute in Order within their Activity. Lower Order runs first.
- `IsActionCompletedOnSuccess` controls whether the action marks itself done after running.
- `IsActivityCompletedOnSuccess` controls whether completing this action also completes the parent activity.
