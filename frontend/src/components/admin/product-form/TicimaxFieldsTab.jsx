import React, { useState, useMemo } from "react";
import { Input } from "../../ui/input";
import { Textarea } from "../../ui/textarea";
import { Switch } from "../../ui/switch";
import { Label } from "../../ui/label";
import { Badge } from "../../ui/badge";
import { ChevronDown, ChevronRight, Search, Database } from "lucide-react";

/**
 * Ticimax 113-alan düzenleme sekmesi.
 * Şema backend'den (/products/meta/ticimax-schema) gruplu gelir; alanlar
 * generic olarak render edilir ve formData.ticimax_fields'a yazılır.
 */
export default function TicimaxFieldsTab({ schema = [], values = {}, onChange }) {
  const [open, setOpen] = useState({ 0: true });
  const [search, setSearch] = useState("");

  const filtered = useMemo(() => {
    if (!search.trim()) return schema;
    const q = search.toLowerCase();
    return schema
      .map((g) => ({
        ...g,
        fields: g.fields.filter(
          (f) => f.label.toLowerCase().includes(q) || f.key.toLowerCase().includes(q)
        ),
      }))
      .filter((g) => g.fields.length > 0);
  }, [schema, search]);

  const filledCount = Object.values(values || {}).filter(
    (v) => v !== "" && v !== null && v !== undefined && v !== 0 && v !== "0"
  ).length;

  if (!schema.length) {
    return (
      <div className="text-sm text-gray-500 py-10 text-center" data-testid="ticimax-empty">
        Ticimax şeması yükleniyor veya bulunamadı.
      </div>
    );
  }

  const set = (key, val) => onChange && onChange(key, val);

  return (
    <div className="space-y-4" data-testid="ticimax-fields-tab">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2 text-sm text-gray-600">
          <Database size={16} className="text-indigo-600" />
          <span>113 Ticimax alanı</span>
          <Badge variant="secondary" data-testid="ticimax-filled-count">{filledCount} dolu</Badge>
        </div>
        <div className="relative w-full sm:w-72">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <Input
            data-testid="ticimax-field-search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Alan ara (ör. SEO, fiyat, barkod)"
            className="pl-9 h-9"
          />
        </div>
      </div>

      {filtered.map((group, gi) => {
        const isOpen = search.trim() ? true : !!open[gi];
        return (
          <div key={group.label} className="border border-gray-200 rounded-xl overflow-hidden">
            <button
              type="button"
              data-testid={`ticimax-group-${gi}`}
              onClick={() => setOpen((p) => ({ ...p, [gi]: !p[gi] }))}
              className="w-full flex items-center justify-between px-4 py-3 bg-gray-50 hover:bg-gray-100 transition-colors"
            >
              <span className="font-medium text-sm text-gray-800">{group.label}</span>
              <div className="flex items-center gap-2">
                <Badge variant="outline" className="text-xs">{group.fields.length}</Badge>
                {isOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
              </div>
            </button>
            {isOpen && (
              <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-4">
                {group.fields.map((f) => {
                  const val = values?.[f.key];
                  const testid = `ticimax-field-${f.key}`;
                  if (f.type === "bool") {
                    return (
                      <div key={f.key} className="flex items-center justify-between border rounded-lg px-3 py-2 bg-white">
                        <Label className="text-xs text-gray-700">{f.label}</Label>
                        <Switch
                          data-testid={testid}
                          checked={String(val) === "1" || val === 1 || val === true}
                          onCheckedChange={(c) => set(f.key, c ? 1 : 0)}
                        />
                      </div>
                    );
                  }
                  if (f.type === "textarea") {
                    return (
                      <div key={f.key} className="md:col-span-2 space-y-1">
                        <Label className="text-xs text-gray-700">{f.label}</Label>
                        <Textarea
                          data-testid={testid}
                          value={val ?? ""}
                          disabled={f.readonly}
                          rows={3}
                          onChange={(e) => set(f.key, e.target.value)}
                        />
                      </div>
                    );
                  }
                  return (
                    <div key={f.key} className="space-y-1">
                      <Label className="text-xs text-gray-700">{f.label}</Label>
                      <Input
                        data-testid={testid}
                        type={f.type === "number" ? "number" : "text"}
                        value={val ?? ""}
                        disabled={f.readonly}
                        onChange={(e) =>
                          set(f.key, f.type === "number" && e.target.value !== "" ? Number(e.target.value) : e.target.value)
                        }
                      />
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
