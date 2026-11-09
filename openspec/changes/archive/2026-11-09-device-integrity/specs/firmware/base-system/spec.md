# Spec Delta

## ADDED Requirements

### Requirement: The image's ucode programs compile
Every ucode script, module and template the image ships SHALL compile with the image's own ucode, each as ucode loads it, so that a program a newer ucode no longer accepts is found when the image is tested, not when it fails to start on the router.

#### Scenario: Compile the image's ucode files
- **WHEN** every ucode file of the image is compiled on the router with the image's ucode: templates as templates, modules as modules, scripts as scripts
- **THEN** every one compiles
