# known_faces/

One sub-folder per registered patient, each containing one or more clear,
front-facing reference photos of that person:

```
known_faces/
├── alice/
│   ├── photo1.jpg
│   └── photo2.jpg
└── bob/
    └── photo1.jpg
```

The folder name is used as the patient's display name (used in speech and
in the Gemini prompts). This directory is created automatically on first
run if it doesn't exist yet - but it will start out empty, so no patient
will be recognised until you add photos here.

As of the receptionist dashboard, this folder is normally populated
automatically: registering a patient there saves their captured photo to
`known_faces/<full name>/reference.jpg` (or `<full name> (<patient ID>)/`
if that name is already taken by another patient), after checking the
photo has exactly one detectable face. Manually dropping photos in here
still works fine for testing without the dashboard running.
