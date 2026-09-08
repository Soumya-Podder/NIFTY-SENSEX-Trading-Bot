"""Disjoint session windows, not a row slice that splits concurrent indices."""


def validation_windows(dates):
    dates=sorted(set(dates))
    if len(dates)<50: return None
    train_end=int(len(dates)*.6)
    validation_end=int(len(dates)*.8)
    return {"train_from":dates[0],"train_to":dates[train_end-1],
        "validation_from":dates[train_end],"validation_to":dates[validation_end-1],
        "test_from":dates[validation_end],"test_to":dates[-1]}
