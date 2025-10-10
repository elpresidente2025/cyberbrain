import React from 'react';
import {
  Grid,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  FormHelperText
} from '@mui/material';

/**
 * FormFieldGroup - 폼 필드 그룹 컴포넌트
 *
 * @param {Array} fields - 필드 정의 배열
 *   [
 *     {
 *       type: 'text' | 'select' | 'number' | 'email' | 'password',
 *       name: string,
 *       label: string,
 *       value: any,
 *       onChange: function,
 *       options: Array (for select),
 *       xs: number,
 *       sm: number,
 *       md: number,
 *       required: boolean,
 *       disabled: boolean,
 *       error: boolean,
 *       helperText: string,
 *       placeholder: string,
 *       multiline: boolean,
 *       rows: number
 *     }
 *   ]
 * @param {number} spacing - Grid spacing
 */
const FormFieldGroup = ({
  fields = [],
  spacing = 3,
  ...props
}) => {
  const renderField = (field) => {
    const {
      type = 'text',
      name,
      label,
      value,
      onChange,
      options = [],
      xs = 12,
      sm,
      md,
      required = false,
      disabled = false,
      error = false,
      helperText,
      placeholder,
      multiline = false,
      rows = 4,
      ...fieldProps
    } = field;

    const gridProps = { xs, sm, md };

    // Select 필드
    if (type === 'select') {
      return (
        <Grid item {...gridProps} key={name}>
          <FormControl fullWidth error={error} disabled={disabled}>
            <InputLabel required={required}>{label}</InputLabel>
            <Select
              name={name}
              value={value}
              onChange={onChange}
              label={label}
              {...fieldProps}
            >
              {options.map((option) => (
                <MenuItem
                  key={option.value}
                  value={option.value}
                >
                  {option.label}
                </MenuItem>
              ))}
            </Select>
            {helperText && <FormHelperText>{helperText}</FormHelperText>}
          </FormControl>
        </Grid>
      );
    }

    // TextField
    return (
      <Grid item {...gridProps} key={name}>
        <TextField
          fullWidth
          type={type}
          name={name}
          label={label}
          value={value}
          onChange={onChange}
          required={required}
          disabled={disabled}
          error={error}
          helperText={helperText}
          placeholder={placeholder}
          multiline={multiline}
          rows={multiline ? rows : undefined}
          {...fieldProps}
        />
      </Grid>
    );
  };

  return (
    <Grid container spacing={spacing} {...props}>
      {fields.map(renderField)}
    </Grid>
  );
};

export default FormFieldGroup;
