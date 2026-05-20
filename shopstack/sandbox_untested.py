def sandbox_only_for_gate_test():
    """Intentionally untested function used only to validate the CI gate.""" 
    return 'this should drag coverage down'

def another_untested_function():
    """Another intentionally untested function used only to validate the CI gate."""
    return 'this should also drag coverage down'

def onemore_covered_function():
    """A function that is covered by tests."""
    return 'this should be covered by tests'

def yet_another_covered_function():
    """Another function that is covered by tests."""
    return 'this should also be covered by tests'
