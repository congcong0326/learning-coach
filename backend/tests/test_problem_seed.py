from backend.app.models.problem import Problem, ProblemCategory, ProblemCategoryItem


def test_problem_model_excludes_source_hash_and_solution_fields() -> None:
    columns = set(Problem.__table__.columns.keys())

    assert {
        "id",
        "frontend_id",
        "slug",
        "title",
        "translated_title",
        "difficulty",
        "statement_md",
        "metadata_json",
        "leetcode_url",
        "is_paid_only",
        "created_at",
        "updated_at",
    } <= columns
    assert "solution_md" not in columns
    assert "source_commit" not in columns
    assert "content_hash" not in columns


def test_category_models_have_only_static_fields() -> None:
    assert set(ProblemCategory.__table__.columns.keys()) == {
        "id",
        "slug",
        "name",
        "description",
        "created_at",
        "updated_at",
    }
    assert set(ProblemCategoryItem.__table__.columns.keys()) == {
        "id",
        "category_id",
        "problem_id",
        "sort_order",
        "created_at",
        "updated_at",
    }
