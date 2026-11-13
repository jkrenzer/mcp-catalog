from mcp_catalog.branching import (
    branch_slug,
    build_image_reference,
    build_server_tag,
    catalog_reference,
)


def test_main_branch_slug_is_main():
    assert branch_slug('main') == 'main'


def test_non_main_branches_get_hash_suffix():
    slug = branch_slug('feature/test')
    assert slug.startswith('feature-test-')
    assert len(slug.split('-')[-1]) == 12


def test_picture_tag_is_build_prefixed():
    tag = build_server_tag('0123456789abcdef0123456789abcdef01234567', '1234', '2')
    assert tag == 'build-0123456789abcdef0123456789abcdef01234567-1234-2'


def test_branch_aware_image_names():
    assert (
        build_image_reference('demo', 'main', 'build-sha-1-1')
        == 'ghcr.io/jkrenzer/mcp-catalog/demo:build-sha-1-1'
    )
    assert build_image_reference('demo', 'feature/test', 'build-sha-1-1').startswith(
        'ghcr.io/jkrenzer/mcp-catalog/feature-test-'
    )
    assert catalog_reference('feature/test').startswith(
        'ghcr.io/jkrenzer/mcp-catalog/feature-test-'
    )
