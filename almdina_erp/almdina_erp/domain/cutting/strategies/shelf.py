from __future__ import annotations

from typing import Any

from ..primitives import make_placed_piece, orientations_for


def pack_shelf_horizontal(
    pieces: list[dict[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
) -> dict[str, Any]:
    sheets: list[dict[str, Any]] = []
    unplaced: list[dict[str, Any]] = []

    def new_sheet() -> dict[str, Any]:
        return {
            "sheet_no": len(sheets) + 1,
            "w": board_w_cm,
            "h": board_h_cm,
            "pieces": [],
            "_x": 0.0,
            "_y": 0.0,
            "_row_h": 0.0,
        }

    def try_place(sheet: dict[str, Any], piece: dict[str, Any]) -> bool:
        for orientation in orientations_for(piece):
            if (
                sheet["_x"] + orientation["w"] <= board_w_cm
                and sheet["_y"] + orientation["h"] <= board_h_cm
            ):
                sheet["pieces"].append(
                    make_placed_piece(
                        piece,
                        sheet["_x"],
                        sheet["_y"],
                        orientation["w"],
                        orientation["h"],
                        orientation["rotated"],
                    )
                )
                sheet["_x"] += orientation["w"] + kerf_cm
                sheet["_row_h"] = max(
                    sheet["_row_h"], orientation["h"] + kerf_cm
                )
                return True
        sheet["_x"] = 0.0
        sheet["_y"] += sheet["_row_h"]
        sheet["_row_h"] = 0.0
        for orientation in orientations_for(piece):
            if (
                sheet["_x"] + orientation["w"] <= board_w_cm
                and sheet["_y"] + orientation["h"] <= board_h_cm
            ):
                sheet["pieces"].append(
                    make_placed_piece(
                        piece,
                        sheet["_x"],
                        sheet["_y"],
                        orientation["w"],
                        orientation["h"],
                        orientation["rotated"],
                    )
                )
                sheet["_x"] += orientation["w"] + kerf_cm
                sheet["_row_h"] = max(
                    sheet["_row_h"], orientation["h"] + kerf_cm
                )
                return True
        return False

    for piece in pieces:
        placed = False
        for sheet in sheets:
            if try_place(sheet, piece):
                placed = True
                break
        if not placed:
            sheet = new_sheet()
            if try_place(sheet, piece):
                sheets.append(sheet)
            else:
                unplaced.append(piece)
    for sheet in sheets:
        sheet.pop("_x", None)
        sheet.pop("_y", None)
        sheet.pop("_row_h", None)
    return {"sheets": sheets, "unplaced": unplaced}


def pack_shelf_vertical(
    pieces: list[dict[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
) -> dict[str, Any]:
    sheets: list[dict[str, Any]] = []
    unplaced: list[dict[str, Any]] = []

    def new_sheet() -> dict[str, Any]:
        return {
            "sheet_no": len(sheets) + 1,
            "w": board_w_cm,
            "h": board_h_cm,
            "pieces": [],
            "_x": 0.0,
            "_y": 0.0,
            "_col_w": 0.0,
        }

    def try_place(sheet: dict[str, Any], piece: dict[str, Any]) -> bool:
        for orientation in orientations_for(piece):
            if (
                sheet["_x"] + orientation["w"] <= board_w_cm
                and sheet["_y"] + orientation["h"] <= board_h_cm
            ):
                sheet["pieces"].append(
                    make_placed_piece(
                        piece,
                        sheet["_x"],
                        sheet["_y"],
                        orientation["w"],
                        orientation["h"],
                        orientation["rotated"],
                    )
                )
                sheet["_y"] += orientation["h"] + kerf_cm
                sheet["_col_w"] = max(
                    sheet["_col_w"], orientation["w"] + kerf_cm
                )
                return True
        sheet["_y"] = 0.0
        sheet["_x"] += sheet["_col_w"]
        sheet["_col_w"] = 0.0
        for orientation in orientations_for(piece):
            if (
                sheet["_x"] + orientation["w"] <= board_w_cm
                and sheet["_y"] + orientation["h"] <= board_h_cm
            ):
                sheet["pieces"].append(
                    make_placed_piece(
                        piece,
                        sheet["_x"],
                        sheet["_y"],
                        orientation["w"],
                        orientation["h"],
                        orientation["rotated"],
                    )
                )
                sheet["_y"] += orientation["h"] + kerf_cm
                sheet["_col_w"] = max(
                    sheet["_col_w"], orientation["w"] + kerf_cm
                )
                return True
        return False

    for piece in pieces:
        placed = False
        for sheet in sheets:
            if try_place(sheet, piece):
                placed = True
                break
        if not placed:
            sheet = new_sheet()
            if try_place(sheet, piece):
                sheets.append(sheet)
            else:
                unplaced.append(piece)
    for sheet in sheets:
        sheet.pop("_x", None)
        sheet.pop("_y", None)
        sheet.pop("_col_w", None)
    return {"sheets": sheets, "unplaced": unplaced}


def pack_shelf_first_fit(
    pieces: list[dict[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
) -> dict[str, Any]:
    sheets: list[dict[str, Any]] = []
    unplaced: list[dict[str, Any]] = []

    def new_sheet() -> dict[str, Any]:
        return {
            "sheet_no": len(sheets) + 1,
            "w": board_w_cm,
            "h": board_h_cm,
            "pieces": [],
            "shelves": [],
        }

    def try_place(sheet: dict[str, Any], piece: dict[str, Any]) -> bool:
        for shelf in sheet["shelves"]:
            for orientation in orientations_for(piece):
                if (
                    orientation["h"] <= shelf["h"]
                    and shelf["x"] + orientation["w"] <= board_w_cm
                ):
                    sheet["pieces"].append(
                        make_placed_piece(
                            piece,
                            shelf["x"],
                            shelf["y"],
                            orientation["w"],
                            orientation["h"],
                            orientation["rotated"],
                        )
                    )
                    shelf["x"] += orientation["w"] + kerf_cm
                    return True
        current_y = 0.0
        for shelf in sheet["shelves"]:
            current_y = max(current_y, shelf["y"] + shelf["h"] + kerf_cm)
        for orientation in orientations_for(piece):
            if (
                current_y + orientation["h"] <= board_h_cm
                and orientation["w"] <= board_w_cm
            ):
                sheet["pieces"].append(
                    make_placed_piece(
                        piece,
                        0.0,
                        current_y,
                        orientation["w"],
                        orientation["h"],
                        orientation["rotated"],
                    )
                )
                sheet["shelves"].append(
                    {
                        "y": current_y,
                        "h": orientation["h"],
                        "x": orientation["w"] + kerf_cm,
                    }
                )
                return True
        return False

    for piece in pieces:
        placed = False
        for sheet in sheets:
            if try_place(sheet, piece):
                placed = True
                break
        if not placed:
            sheet = new_sheet()
            if try_place(sheet, piece):
                sheets.append(sheet)
            else:
                unplaced.append(piece)
    for sheet in sheets:
        sheet.pop("shelves", None)
    return {"sheets": sheets, "unplaced": unplaced}


def pack_shelf_next_fit(
    pieces: list[dict[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
) -> dict[str, Any]:
    sheets: list[dict[str, Any]] = []
    unplaced: list[dict[str, Any]] = []
    sheet: dict[str, Any] | None = None
    x = y = row_h = 0.0

    def start_new_sheet() -> dict[str, Any]:
        nonlocal sheet, x, y, row_h
        sheet = {
            "sheet_no": len(sheets) + 1,
            "w": board_w_cm,
            "h": board_h_cm,
            "pieces": [],
        }
        sheets.append(sheet)
        x = y = row_h = 0.0
        return sheet

    def place(piece: dict[str, Any], orientation: dict[str, Any]) -> None:
        nonlocal x, row_h
        assert sheet is not None
        sheet["pieces"].append(
            make_placed_piece(
                piece,
                x,
                y,
                orientation["w"],
                orientation["h"],
                orientation["rotated"],
            )
        )
        x += orientation["w"] + kerf_cm
        row_h = max(row_h, orientation["h"] + kerf_cm)

    for piece in pieces:
        if sheet is None:
            start_new_sheet()
        placed = False
        for orientation in orientations_for(piece):
            if x + orientation["w"] <= board_w_cm and y + orientation["h"] <= board_h_cm:
                place(piece, orientation)
                placed = True
                break
        if not placed:
            x = 0.0
            y += row_h
            row_h = 0.0
            for orientation in orientations_for(piece):
                if x + orientation["w"] <= board_w_cm and y + orientation["h"] <= board_h_cm:
                    place(piece, orientation)
                    placed = True
                    break
        if not placed:
            start_new_sheet()
            for orientation in orientations_for(piece):
                if x + orientation["w"] <= board_w_cm and y + orientation["h"] <= board_h_cm:
                    place(piece, orientation)
                    placed = True
                    break
        if not placed:
            unplaced.append(piece)
    return {"sheets": sheets, "unplaced": unplaced}


__all__ = [
    "pack_shelf_first_fit",
    "pack_shelf_horizontal",
    "pack_shelf_next_fit",
    "pack_shelf_vertical",
]
