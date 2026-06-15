class Job {
  final int? id;
  final String title;
  final String organization;
  final String totalVacancies;
  final DateTime? startDate;
  final DateTime lastDate;
  final String feeDetails;
  final String eligibility;
  final String officialApplyLink;

  Job({
    this.id,
    required this.title,
    required this.organization,
    required this.totalVacancies,
    this.startDate,
    required this.lastDate,
    required this.feeDetails,
    required this.eligibility,
    required this.officialApplyLink,
  });

  factory Job.fromJson(Map<String, dynamic> json) {
    String parseDate(String? dateStr) {
      if (dateStr == null || dateStr.isEmpty) {
        return DateTime.now().add(Duration(days: 365)).toIso8601String().split('T')[0];
      }
      return dateStr;
    }

    return Job(
      id: json['id'] as int?,
      title: json['title'] as String? ?? 'Unknown',
      organization: json['organization'] as String? ?? 'Other',
      totalVacancies: json['total_vacancies'] as String? ?? 'Not specified',
      startDate: json['start_date'] != null
          ? DateTime.tryParse(json['start_date'] as String)
          : null,
      lastDate: DateTime.parse(parseDate(json['last_date'] as String?)),
      feeDetails: json['fee_details'] as String? ?? 'As per official notification',
      eligibility: json['eligibility'] as String? ?? 'As per official notification',
      officialApplyLink: json['official_apply_link'] as String? ?? '',
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'title': title,
      'organization': organization,
      'total_vacancies': totalVacancies,
      'start_date': startDate?.toIso8601String().split('T')[0],
      'last_date': lastDate.toIso8601String().split('T')[0],
      'fee_details': feeDetails,
      'eligibility': eligibility,
      'official_apply_link': officialApplyLink,
    };
  }
}