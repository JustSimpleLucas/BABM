// CsvSchema.h

#ifndef ABM_OUTPUT_CSV_SCHEMA_H
#define ABM_OUTPUT_CSV_SCHEMA_H

#include <cstddef>
#include <ostream>

namespace abm::output_detail {

/**
 * One CSV column: its header name paired with the function that writes its value.
 *
 * Pairing the two is the whole point. Each writer used to spell its schema
 * twice — once as a header string literal and once as an ordered chain of
 * stream insertions — so a column added to one and not the other silently
 * shifted every later value into the wrong column. That corruption compiles
 * cleanly, and the archive validators cannot see it because they check the
 * header alone. With one table there is no second list to disagree with.
 *
 * `emit` is a plain function pointer rather than a std::function so a capture
 * cannot smuggle per-row state into the schema, and so writing a row costs no
 * allocation on the trade-ledger path, which runs to hundreds of thousands of
 * rows.
 *
 * Emitting nothing is how a column reports "no value on this row"; the commas
 * come from the table, so partially populated rows need no field-count padding.
 */
template <typename Row> struct CsvColumn {
    const char* name;
    void (*emit)(std::ostream& out, const Row& row);
};

/** Writes the comma-separated header line for a column table. */
template <typename Row, std::size_t ColumnCount>
void writeCsvHeader(std::ostream& out, const CsvColumn<Row> (&columns)[ColumnCount]) {
    for (std::size_t columnIndex = 0; columnIndex < ColumnCount; ++columnIndex) {
        if (columnIndex > 0) {
            out << ',';
        }
        out << columns[columnIndex].name;
    }
    out << '\n';
}

/** Writes one data row in column-table order. */
template <typename Row, std::size_t ColumnCount>
void writeCsvRow(std::ostream& out, const CsvColumn<Row> (&columns)[ColumnCount], const Row& row) {
    for (std::size_t columnIndex = 0; columnIndex < ColumnCount; ++columnIndex) {
        if (columnIndex > 0) {
            out << ',';
        }
        columns[columnIndex].emit(out, row);
    }
    out << '\n';
}

} // namespace abm::output_detail

#endif // ABM_OUTPUT_CSV_SCHEMA_H
