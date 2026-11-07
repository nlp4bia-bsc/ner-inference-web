"""Read-only terminology setup diagnostics, without importing NLP or reading terms."""

from app.services.normalization_catalog import CATEGORIES, NormalizationCatalog


def normalization_status(settings):
    root = settings.normalization_gazetteer_dir.resolve()
    result = {
        "enabled": settings.normalization_enabled,
        "directory": str(root),
        "manifest_exists": False,
    }
    try:
        result["manifest_exists"] = (root / "manifest.json").is_file()
        result["parquet_files"] = sum(1 for _ in root.rglob("*.parquet")) if root.is_dir() else 0
        catalog = NormalizationCatalog(settings)
        result["registered_resources"] = len(catalog.resources)
        result["languages"] = sorted({key[0] for key in catalog.resources})
        result["resources"] = [
            {"language": language, "entity": entity, "file_exists": row["file"].is_file()}
            for (language, entity), row in sorted(catalog.resources.items())
        ]
        result["spanish"] = [
            {
                "entity": entity,
                "available": bool(catalog.resolve("es", entity)),
                "reason_code": None
                if catalog.resolve("es", entity)
                else catalog.unavailability_reason("es", entity),
            }
            for entity in CATEGORIES
        ]
        result["import_required"] = not catalog.imported or not catalog.resources
    except PermissionError:
        result["error_code"] = "TERMINOLOGY_ACCESS_DENIED"
    except (OSError, ValueError, KeyError, TypeError):
        result["error_code"] = "TERMINOLOGY_CONFIGURATION_INVALID"
    return result
