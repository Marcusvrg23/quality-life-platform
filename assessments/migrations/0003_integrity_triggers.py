"""PostgreSQL guards for writes that bypass Django model methods."""

from django.db import migrations

SQL = r"""
CREATE FUNCTION assessments_require_draft(vid bigint) RETURNS void AS $$
DECLARE current_status text;
BEGIN
    SELECT status INTO current_status FROM assessments_questionnaireversion
    WHERE id = vid FOR UPDATE;
    IF current_status IS DISTINCT FROM 'DRAFT' THEN
        RAISE EXCEPTION 'Published questionnaire configuration is immutable' USING ERRCODE = '23514';
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE FUNCTION assessments_configuration_guard() RETURNS trigger AS $$
DECLARE old_version bigint; new_version bigint;
BEGIN
    IF TG_TABLE_NAME = 'assessments_questionnairepillar' THEN
        IF TG_OP <> 'INSERT' THEN old_version := OLD.questionnaire_id; END IF;
        IF TG_OP <> 'DELETE' THEN new_version := NEW.questionnaire_id; END IF;
    ELSIF TG_TABLE_NAME = 'assessments_question' THEN
        IF TG_OP <> 'INSERT' THEN
            SELECT questionnaire_id INTO old_version FROM assessments_questionnairepillar
            WHERE id = OLD.questionnaire_pillar_id;
        END IF;
        IF TG_OP <> 'DELETE' THEN
            SELECT questionnaire_id INTO new_version FROM assessments_questionnairepillar
            WHERE id = NEW.questionnaire_pillar_id;
        END IF;
    ELSE
        IF TG_OP <> 'INSERT' THEN
            SELECT qp.questionnaire_id INTO old_version FROM assessments_question q
            JOIN assessments_questionnairepillar qp ON qp.id = q.questionnaire_pillar_id
            WHERE q.id = OLD.question_id;
        END IF;
        IF TG_OP <> 'DELETE' THEN
            SELECT qp.questionnaire_id INTO new_version FROM assessments_question q
            JOIN assessments_questionnairepillar qp ON qp.id = q.questionnaire_pillar_id
            WHERE q.id = NEW.question_id;
        END IF;
    END IF;
    IF old_version IS NOT NULL THEN PERFORM assessments_require_draft(old_version); END IF;
    IF new_version IS NOT NULL AND new_version IS DISTINCT FROM old_version THEN
        PERFORM assessments_require_draft(new_version);
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER assessments_qp_guard BEFORE INSERT OR UPDATE OR DELETE ON assessments_questionnairepillar
FOR EACH ROW EXECUTE FUNCTION assessments_configuration_guard();
CREATE TRIGGER assessments_question_guard BEFORE INSERT OR UPDATE OR DELETE ON assessments_question
FOR EACH ROW EXECUTE FUNCTION assessments_configuration_guard();
CREATE TRIGGER assessments_option_guard BEFORE INSERT OR UPDATE OR DELETE ON assessments_questionoption
FOR EACH ROW EXECUTE FUNCTION assessments_configuration_guard();

CREATE FUNCTION assessments_pillar_guard() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Approved pillar is immutable' USING ERRCODE = '23514';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER assessments_pillar_immutable BEFORE UPDATE OR DELETE ON assessments_pillar
FOR EACH ROW EXECUTE FUNCTION assessments_pillar_guard();

CREATE FUNCTION assessments_questionnaire_guard() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'DRAFT' THEN
            RAISE EXCEPTION 'New questionnaire must be a draft' USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    IF OLD.status <> 'DRAFT' THEN
        IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'Published questionnaire is immutable' USING ERRCODE = '23514';
        END IF;
        IF OLD.status <> 'PUBLISHED' OR NEW.status <> 'RETIRED'
            OR ROW(NEW.code, NEW.version, NEW.title, NEW.scoring_version)
                IS DISTINCT FROM ROW(OLD.code, OLD.version, OLD.title, OLD.scoring_version) THEN
            RAISE EXCEPTION 'Published questionnaire is immutable' USING ERRCODE = '23514';
        END IF;
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER assessments_questionnaire_immutable BEFORE INSERT OR UPDATE OR DELETE ON assessments_questionnaireversion
FOR EACH ROW EXECUTE FUNCTION assessments_questionnaire_guard();

CREATE FUNCTION assessments_assessment_guard() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'IN_PROGRESS' THEN
            RAISE EXCEPTION 'Assessment must start in progress' USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    IF OLD.status = 'COMPLETED' THEN
        RAISE EXCEPTION 'Completed assessment is immutable' USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'UPDATE' AND ROW(NEW.user_id, NEW.organization_id, NEW.questionnaire_version_id)
        IS DISTINCT FROM ROW(OLD.user_id, OLD.organization_id, OLD.questionnaire_version_id) THEN
        RAISE EXCEPTION 'Assessment identity is immutable' USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER assessments_assessment_immutable BEFORE INSERT OR UPDATE OR DELETE ON assessments_assessment
FOR EACH ROW EXECUTE FUNCTION assessments_assessment_guard();

CREATE FUNCTION assessments_answer_guard() RETURNS trigger AS $$
DECLARE current_status text; version_id bigint; option_question_id bigint;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        SELECT status INTO current_status FROM assessments_assessment WHERE id = OLD.assessment_id FOR UPDATE;
        IF current_status <> 'IN_PROGRESS' THEN
            RAISE EXCEPTION 'Completed assessment answers are immutable' USING ERRCODE = '23514';
        END IF;
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    SELECT status, questionnaire_version_id INTO current_status, version_id
    FROM assessments_assessment WHERE id = NEW.assessment_id FOR UPDATE;
    IF current_status <> 'IN_PROGRESS' THEN
        RAISE EXCEPTION 'Completed assessment answers are immutable' USING ERRCODE = '23514';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM assessments_question q
        JOIN assessments_questionnairepillar qp ON qp.id = q.questionnaire_pillar_id
        WHERE q.id = NEW.question_id AND qp.questionnaire_id = version_id
    ) THEN
        RAISE EXCEPTION 'Question belongs to another version' USING ERRCODE = '23514';
    END IF;
    SELECT question_id INTO option_question_id FROM assessments_questionoption WHERE id = NEW.selected_option_id;
    IF option_question_id IS DISTINCT FROM NEW.question_id THEN
        RAISE EXCEPTION 'Option belongs to another question' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER assessments_answer_immutable BEFORE INSERT OR UPDATE OR DELETE ON assessments_answer
FOR EACH ROW EXECUTE FUNCTION assessments_answer_guard();

CREATE FUNCTION assessments_result_guard() RETURNS trigger AS $$
DECLARE current_status text;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'Persisted result is immutable' USING ERRCODE = '23514';
    END IF;
    IF TG_TABLE_NAME = 'assessments_assessmentresult' THEN
        SELECT status INTO current_status FROM assessments_assessment
        WHERE id = NEW.assessment_id FOR UPDATE;
    ELSE
        SELECT a.status INTO current_status FROM assessments_assessment a
        JOIN assessments_assessmentresult r ON r.assessment_id = a.id
        WHERE r.id = NEW.assessment_result_id FOR UPDATE OF a;
    END IF;
    IF current_status <> 'IN_PROGRESS' THEN
        RAISE EXCEPTION 'Cannot add result to completed assessment' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER assessments_result_immutable BEFORE INSERT OR UPDATE OR DELETE ON assessments_assessmentresult
FOR EACH ROW EXECUTE FUNCTION assessments_result_guard();
CREATE TRIGGER assessments_pillar_result_immutable BEFORE INSERT OR UPDATE OR DELETE ON assessments_pillarresult
FOR EACH ROW EXECUTE FUNCTION assessments_result_guard();
"""

REVERSE_SQL = """
DROP TRIGGER assessments_pillar_result_immutable ON assessments_pillarresult;
DROP TRIGGER assessments_result_immutable ON assessments_assessmentresult;
DROP TRIGGER assessments_answer_immutable ON assessments_answer;
DROP TRIGGER assessments_assessment_immutable ON assessments_assessment;
DROP TRIGGER assessments_questionnaire_immutable ON assessments_questionnaireversion;
DROP TRIGGER assessments_pillar_immutable ON assessments_pillar;
DROP TRIGGER assessments_option_guard ON assessments_questionoption;
DROP TRIGGER assessments_question_guard ON assessments_question;
DROP TRIGGER assessments_qp_guard ON assessments_questionnairepillar;
DROP FUNCTION assessments_result_guard();
DROP FUNCTION assessments_answer_guard();
DROP FUNCTION assessments_assessment_guard();
DROP FUNCTION assessments_questionnaire_guard();
DROP FUNCTION assessments_pillar_guard();
DROP FUNCTION assessments_configuration_guard();
DROP FUNCTION assessments_require_draft(bigint);
"""


class Migration(migrations.Migration):
    dependencies = [("assessments", "0002_nine_pillars")]  # noqa: RUF012
    operations = [migrations.RunSQL(SQL, REVERSE_SQL)]  # noqa: RUF012
