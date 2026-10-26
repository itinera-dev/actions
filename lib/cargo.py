"""Cargo workspaces, as `cargo metadata --no-deps --format-version 1` describes them."""


def publishable_members(metadata):
    """The packages of the workspace that `metadata` describes that may be published: its members whose manifest
    does not say `publish = false`."""
    members = set(metadata["workspace_members"])
    return [package for package in metadata["packages"] if package["id"] in members and package.get("publish") != []]
